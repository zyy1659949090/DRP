'''A module containing decorators which are useful in most test cases for the DRP'''

from chemspipy import ChemSpider
from DRP.models import Compound, LabGroup, ChemicalClass
from django.contrib.auth.models import User
from django.conf import settings

def createsUser(username, password):
  '''A class decorator that creates a user'''

  def _createsUSer(c):

    _oldSetup = c.setUp
    _oldTearDown = c.tearDown

    def setUp(self):
      user = User.objects.create_user(username=username, password=password)
      user.save()
      _oldSetup(self)

    def tearDown(self):
      _oldTearDown(self)
      User.objects.filter(username=username).delete()

    c.setUp = setUp
    c.tearDown = tearDown
    return c
  return _createsUser

def createsCompound(abbrev, csid, classLabel, labTitle):

  def _createsCompound(c):

    _oldSetup = c.setUp
    _oldTearDown = c.tearDown

    compound = Compound(abbrev=abbrev, CSID=csid, chemicalClass=ChemicalClass.objects.get(label=classLabel), labGroup=LabGroup.objects.get(title=labTitle))

    def setUp(self):
      _oldSetup(self)
      compound.save()

    def tearDown(self):
      _oldTearDown(self)
      compound.delete()

    c.setUp = setUp
    c.tearDown = tearDown
    return c
  return _createsCompound

def createsChemicalClass(label, description):
  '''A class decorator that creates a test chemical class for the addition of compounds into the database'''

  def _createsChemicalClass(c):

    _oldSetup = c.setUp
    _oldTearDown = c.tearDown

    chemicalClass = ChemicalClass(label=label, description=description)

    def setUp(self):
      chemicalClass.save()
      _oldSetup(self)

    def tearDown(self):
      chemicalClass.delete()
      _oldTearDown(self)

    c.setUp = setUp
    c.tearDown = tearDown
    return c
  return _createsChemicalClass

def joinsLabGroup(username, labGroupTitle):
  '''A class decorator that creates a test lab group with labGroupTitle as it's title and assigns user identified by
  username to that lab group'''
  def _joinsLabGroup(c):
    _oldSetup = c.setUp
    _oldTearDown = c.tearDown

    labGroup = LabGroup(title=labGroupTitle, address='War drobe', email='Aslan@example.com', access_code='new_magic')

    def setUp(self):
      user = User.objects.get(username=username)
      labGroup.save()
      user.labgroup_set.add(labGroup)
      _oldSetup(self)

    def tearDown(self):
      _oldTearDown(self)
      labGroup.delete()

    c.setUp = setUp
    c.tearDown = tearDown
    return c
  return _joinsLabGroup

def signsExampleLicense(username):
  '''A class decorator that creates a test license and makes the user specified by username sign it on setUp'''
  def _signsExampleLicense(c):

    _oldSetup = c.setUp
    _oldTearDown = c.tearDown
     
    license = License(text='This is an example license used in a test', effectiveDate=date.today() - timedelta(1))

    def setUp(self):
      user = User.objects.get(username=username)
      license.save()
      self.agreement = LicenseAgreement(user=user, text=license)
      self.agreement.save()
      _oldSetup(self)

    def tearDown(self):
      self.agreement.delete()
      license.delete()
      _oldTearDown(self)

    c.setUp = setUp
    c.tearDown = tearDown
    return c
  return _signsExampleLicense
