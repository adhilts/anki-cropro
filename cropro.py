import re

from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo
from anki.utils import stripHTMLMedia
from anki import Collection
from anki.notes import Note

ENABLE_DEBUG_LOG = False
logfile = None

def logDebug(s):
    if not ENABLE_DEBUG_LOG:
        return

    global logfile
    if not logfile:
        fn = os.path.join(mw.pm.base, 'cropro.log')
        logfile = open(fn, 'a')
    logfile.write(s + '\n')
    logfile.flush()

# backported from Anki 2.1 anki/utils.py
def htmlToTextLine(s):
    s = s.replace("<br>", " ")
    s = s.replace("<br />", " ")
    s = s.replace("<div>", " ")
    s = s.replace("\n", " ")
    s = re.sub("\[sound:[^]]+\]", "", s)
    s = re.sub("\[\[type:[^]]+\]\]", "", s)
    s = stripHTMLMedia(s)
    s = s.strip()
    return s

def getOtherProfileNames():
    profiles = mw.pm.profiles()
    profiles.remove(mw.pm.name)
    return profiles

def openProfileCollection(name):
    # NOTE: this code is based on aqt/profiles.py; we can't really re-use what's there
    collectionFilename = os.path.join(mw.pm.base, name, 'collection.anki2')
    return Collection(collectionFilename)

class MainDialog(QDialog):
    def __init__(self):
        super(MainDialog, self).__init__()

        self.otherProfileName = None
        self.otherProfileCollection = None

        self.initUI()

    def initUI(self):
        self.otherProfileDeckCombo = QComboBox()

        self.otherProfileCombo = QComboBox()
        otherProfileNames = getOtherProfileNames()
        if otherProfileNames:
            self.otherProfileCombo.addItems(otherProfileNames)
            self.otherProfileCombo.currentIndexChanged.connect(self.otherProfileComboChange)
            self.handleSelectOtherProfile(otherProfileNames[0])
        else:
            # TODO: handle this case
            pass

        otherProfileDeckRow = QHBoxLayout()
        otherProfileDeckRow.addWidget(QLabel('Import From Profile:'))
        otherProfileDeckRow.addWidget(self.otherProfileCombo)
        otherProfileDeckRow.addWidget(QLabel('Deck:'))
        otherProfileDeckRow.addWidget(self.otherProfileDeckCombo)
        otherProfileDeckRow.addStretch(1)

        self.filterEdit = QLineEdit()
        self.filterEdit.setPlaceholderText('<text to filter by>')

        filterButton = QPushButton('Filter')

        filterRow = QHBoxLayout()
        filterRow.addWidget(self.filterEdit)
        filterRow.addWidget(filterButton)

        self.noteListView = QListView()
        self.noteListView.setResizeMode(self.noteListView.Fixed)
        self.noteListModel = QStandardItemModel(self.noteListView)
        self.noteListView.setModel(self.noteListModel)
        self.noteListView.setSelectionMode(self.noteListView.ExtendedSelection)

        currentProfileNameLabel = QLabel(mw.pm.name)
        currentProfileNameLabelFont = QFont()
        currentProfileNameLabelFont.setBold(True)
        currentProfileNameLabel.setFont(currentProfileNameLabelFont)

        self.currentProfileDeckCombo = QComboBox()
        currentProfileDecks = mw.col.decks.all()
        currentProfileDecks.sort(key=lambda d: d['name'])
        selectedDeckId = mw.col.decks.selected()
        selectedIndex = None
        for idx, deck in enumerate(currentProfileDecks):
            self.currentProfileDeckCombo.addItem(deck['name'], deck['id'])
            if deck['id'] == selectedDeckId:
                selectedIndex = idx
        if selectedIndex is not None:
            self.currentProfileDeckCombo.setCurrentIndex(selectedIndex)

        statsRow = QVBoxLayout()

        self.statSuccessLabel = QLabel()
        self.statSuccessLabel.setStyleSheet('QLabel { color : green; }')
        self.statSuccessLabel.hide()
        statsRow.addWidget(self.statSuccessLabel)

        self.statNoMatchingModelLabel = QLabel()
        self.statNoMatchingModelLabel.setStyleSheet('QLabel { color : red; }')
        self.statNoMatchingModelLabel.hide()
        statsRow.addWidget(self.statNoMatchingModelLabel)

        self.statDupeLabel = QLabel()
        self.statDupeLabel.setStyleSheet('QLabel { color : orange; }')
        self.statDupeLabel.hide()
        statsRow.addWidget(self.statDupeLabel)

        importRow = QHBoxLayout()
        importRow.addWidget(QLabel('Into Profile:'))
        importRow.addWidget(currentProfileNameLabel)
        importRow.addWidget(QLabel('Deck:'))
        importRow.addWidget(self.currentProfileDeckCombo)

        importButton = QPushButton('Import')
        importButton.clicked.connect(self.importButtonClick)

        importRow.addWidget(importButton)
        importRow.addStretch(1)

        mainVbox = QVBoxLayout()
        mainVbox.addLayout(otherProfileDeckRow)
        mainVbox.addLayout(filterRow)
        mainVbox.addWidget(self.noteListView)
        mainVbox.addLayout(statsRow)
        mainVbox.addLayout(importRow)

        self.otherProfileDeckCombo.currentIndexChanged.connect(self.updateNotesList)
        filterButton.clicked.connect(self.updateNotesList)

        self.setLayout(mainVbox)

        self.setWindowTitle('Cross Profile Import')
        self.exec_()

    def otherProfileComboChange(self):
        newProfileName = self.otherProfileCombo.currentText()
        self.handleSelectOtherProfile(newProfileName)

    def updateNotesList(self):
        otherProfileDeckName = self.otherProfileDeckCombo.currentText()
        self.noteListModel.clear()
        if otherProfileDeckName:
            # deck was selected, fill list

            # build query string
            query = 'deck:"' + otherProfileDeckName + '"' # quote name in case it has spaces

            # get filter text, if any
            filterText = self.filterEdit.text()
            if filterText:
                query += ' "%s"' % filterText

            noteIds = self.otherProfileCollection.findNotes(query)
            # TODO: we could try to do this in a single sqlite query, but would be brittle
            for noteId in noteIds:
                note = self.otherProfileCollection.getNote(noteId)
                item = QStandardItem()
                item.setText(htmlToTextLine(note.fields[0]))
                item.setData(noteId)
                self.noteListModel.appendRow(item)
        else:
            # deck was unselected, leave list cleared
            pass

    def handleSelectOtherProfile(self, name):
        # Close current collection object, if any
        if self.otherProfileCollection:
            self.otherProfileCollection.close()
            self.otherProfileCollection = None

        self.otherProfileName = name
        self.otherProfileCollection = openProfileCollection(name)

        self.otherProfileDeckCombo.clear()
        self.otherProfileDeckCombo.addItems(sorted(self.otherProfileCollection.decks.allNames()))

    def importButtonClick(self):
        logDebug('beginning import')

        currentProfileDeckId = self.currentProfileDeckCombo.itemData(self.currentProfileDeckCombo.currentIndex())
        logDebug('current profile deck id %d' % currentProfileDeckId)

        # get the note ids of all selected notes
        noteIds = [self.noteListModel.itemFromIndex(idx).data() for idx in self.noteListView.selectedIndexes()]

        # clear the selection
        self.noteListView.clearSelection()

        logDebug('importing %d notes' % len(noteIds))

        statSuccess = 0
        statNoMatchingModel = 0
        statDupe = 0

        for nid in noteIds:
            # load the note
            logDebug('import note id %d' % nid)
            otherNote = self.otherProfileCollection.getNote(nid)

            # find the model name of the note
            modelName = otherNote._model['name']
            logDebug('model name %r' % modelName)

            # find a model in current profile that matches the name of model from other profile
            matchingModel = mw.col.models.byName(modelName)
            logDebug('matching model %s' % matchingModel)

            # there may not be a model with the same name
            if matchingModel is None:
                statNoMatchingModel += 1
                continue

            # TODO: ensure that field map is same between two models (or same length?), otherwise skip

            # create a new note object
            newNote = Note(mw.col, matchingModel)
            logDebug('new note %s %s' % (newNote.id, newNote.mid))

            # set the deck that the note will generate cards into
            newNote.model()['did'] = currentProfileDeckId

            # copy field values into new note object
            newNote.fields = otherNote.fields[:] # list of strings, so clone it

            # check if note is dupe of existing one
            if newNote.dupeOrEmpty():
                logDebug('dupe')
                statDupe += 1
                continue

            addedCardCount = mw.col.addNote(newNote)

            statSuccess += 1

        mw.requireReset()

        if statSuccess:
            self.statSuccessLabel.setText('%d notes successfully imported' % statSuccess)
            self.statSuccessLabel.show()
        else:
            self.statSuccessLabel.hide()
        if statNoMatchingModel:
            self.statNoMatchingModelLabel.setText('%d notes failed to import because there is no matching Note Type in the current profile' % statNoMatchingModel)
            self.statNoMatchingModelLabel.show()
        else:
            self.statNoMatchingModelLabel.hide()
        if statDupe:
            self.statDupeLabel.setText('%d notes were duplicates, and skipped' % statDupe)
            self.statDupeLabel.show()
        else:
            self.statDupeLabel.hide()

    def closeEvent(self, event):
        if self.otherProfileCollection:
            self.otherProfileCollection.close()

        mw.maybeReset()

        super(MainDialog, self).closeEvent(event)

def addMenuItem():
    a = QAction(mw)
    a.setText('Cross Profile Import')
    mw.form.menuTools.addAction(a)
    a.triggered.connect(MainDialog)


addMenuItem()
