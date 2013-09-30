from django.forms import *
from django.core import validators
from django.core.cache import cache

from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm

from django.db import models

from validation import *
import random, string, datetime
from data_config import CONFIG
import chemspipy


#############  CACHE VALIDATION and ACCESS  ###########################
#Strip any spaces from the lab group title and/or the keys on cache access.
def set_cache(lab_group, key, value, duration=604800): #Default duration is 1 week.
	condensed_lab = lab_group.lab_title.replace(" ","")
	if key: condensed_key = key.replace(" ","") #Don't try to .replace None-types.
	else: condensed_key = None
	cache.set("{}|{}".format(condensed_lab, condensed_key), value, duration)


def get_cache(lab_group, key):
	condensed_lab = lab_group.lab_title.replace(" ","")
	condensed_key = key.replace(" ","") #Key must be a string.
	return cache.get("{}|{}".format(condensed_lab, condensed_key))

############### USER and LAB INTEGRATION #######################
ACCESS_CODE_MAX_LENGTH = 20 #Designates the max_length of access_codes

#Create a random alphanumeric code of specified length.
def get_random_code(length = ACCESS_CODE_MAX_LENGTH):
	return "".join(
			random.choice(
				string.letters + string.digits
			) for i in range(length))


class Lab_Group(models.Model):
	lab_title = models.CharField(max_length=200)

	access_code = models.CharField(max_length=ACCESS_CODE_MAX_LENGTH,
		default=get_random_code)

	def __unicode__(self):
		return self.lab_title


############### USER CREATION #######################
class Lab_Member(models.Model):
	user = models.OneToOneField(User, unique=True) ###Allow lab member to switch?
	lab_group = models.ForeignKey(Lab_Group)

	def __unicode__(self):
		return self.user.username


class UserForm(ModelForm):
	username = CharField(label="Username", required=True,
		widget=TextInput(attrs={'class':'form_text'}))
	password = CharField(label="Password", required=True,
		widget=PasswordInput(attrs={'class':'form_text'}))
	first_name = CharField(label="First Name", required=True,
		widget=TextInput(attrs={'class':'form_text'}))
	last_name = CharField(label="Last Name", required=True,
		widget=TextInput(attrs={'class':'form_text'}))
	email = EmailField(label="Email", required=True,
		widget=TextInput(attrs={'class':'form_text'}))

	class Meta:
		model = User
		fields = ("username", "email",
			"first_name", "last_name",
			"password")

	#Hash the user's password upon save.
	def save(self, commit=True):
		user = super(UserForm, self).save(commit=False)
		user.set_password(self.cleaned_data["password"])
		if commit:
			user.save()
		return user

class UserProfileForm(ModelForm):
	#Enumerate all of the lab titles.

	lab_group = ModelChoiceField(queryset=Lab_Group.objects.all(),
		label="Lab Group", required=True,
		widget=Select(attrs={'class':'form_text'}))
	access_code = CharField(label="Access Code", required=True,
		max_length=ACCESS_CODE_MAX_LENGTH,
		widget=TextInput(attrs={'class':'form_text'}))

	class Meta:
		model = Lab_Member
		app_label = "formsite"
		fields = ["lab_group"]


################ COMPOUND GUIDE ########################
class CompoundEntry(models.Model):
	abbrev = models.CharField("Abbreviation", max_length=100) ###repr in admin 500 error
	compound = models.CharField("Compound", max_length=100)
	CAS_ID = models.CharField("CAS ID", max_length=13, blank=True)
	compound_type = models.CharField("Type", max_length=10)

	lab_group = models.ForeignKey(Lab_Group, unique=False)
		###User foreign key as well
	def __unicode__(self):
		if self.compound == self.abbrev:
			return u"{} (--> same) (LAB: {})".format(self.abbrev, self.lab_group.lab_title)
		return u"{} --> {} (LAB: {})".format(self.abbrev, self.compound, self.lab_group.lab_title)

TYPE_CHOICES = [[opt,opt] for opt in edit_choices["typeChoices"]]

class CompoundGuideForm(ModelForm):
	compound = CharField(widget=TextInput(
		attrs={'class':'form_text',
		"title":"What the abbreviation stands for."}))
	abbrev = CharField(widget=TextInput(
		attrs={'class':'form_text form_text_short',
		"title":"The abbreviation you want to type."}))
	CAS_ID = CharField(label="CAS ID", widget=TextInput(
		attrs={'class':'form_text',
		"title":"The CAS ID of the compound if available."}),
		required=False)
	compound_type = ChoiceField(label="Type", choices = TYPE_CHOICES,
		widget=Select(attrs={'class':'form_text dropDownMenu',
		"title":"Choose the compound type: <br/> --Organic <br/> --Inorganic<br/>--pH Changing<br/>--Oxalate-like<br/>"+
		"--Solute<br/>--Water"}))
	###NEED TO ADD SMILES? PERHAPS JUST AUTO-GEN...

	class Meta:
		model = CompoundEntry
		exclude = ("lab_group",)

	def __init__(self, lab_group=None, *args, **kwargs):
		super(CompoundGuideForm, self).__init__(*args, **kwargs)
		self.lab_group = lab_group

	def save(self, commit=True):
		entry = super(CompoundGuideForm, self).save(commit=False)
		entry.lab_group = self.lab_group
		if commit:
			entry.save()
		return entry

	def clean(self): ################################################################## WORK HERE, CASEY : ) --Past Casey
		#Initialize the variables needed for the cleansing process.
		dirty_data = super(CompoundGuideForm, self).clean() #Get the available raw (dirty) data
		clean_data = {} #Keep track of cleaned fields

		try:
			clean_CAS_ID = dirty_data["CAS_ID"].replace(" ", "-").replace("/", "-").replace("_", "-")
			###Try to find a CAS ID here?
			assert(clean_CAS_ID)
			#Check that the CAS ID has three hyphen-delineated parts.
			if len(clean_CAS_ID.split("-")) != 3:
				self._errors["CAS_ID"] = self.error_class(
					["CAS ID requires three distinct parts."])
			#Check that only numbers are present.
			elif not clean_CAS_ID.replace("-","").isdigit():
				self._errors["CAS_ID"] = self.error_class(
					["CAS ID may only have numeric characters."])
			clean_data["CAS_ID"] = clean_CAS_ID
		except Exception as e:
			#If no CAS_ID is found, store a blank value.
			clean_data["CAS_ID"] = ""

		other_fields = ["abbrev", "compound", "compound_type"]
		for field in other_fields:
			try:
				clean_data[field] = dirty_data[field]
			except:
				self._errors[field] = self.error_class(
					["This field cannot be blank."])

		##If the compound was entered, make sure we can get a SMILES from it.
		if not self._errors.get("compound"):
			try:
				#Lookup the compound in the ChemSpider Database
				chemspider_data = chemspipy.find_one(clean_data["compound"])
				smiles = chemspider_data.smiles
				###Possible? Might need to add to chemspipy.py
				###if not clean_data["CAS_ID"]:
					###clean_data["CAS_ID"] = chemspider_data.cas
			except Exception as e:
				self._errors["compound"] = self.error_class(
					["Could not find this molecule. Try a different name."])


		#If an abbreviation is duplicated.
		###if clean_data["abbrev"] in abbrev_dict:###NO ACCESS TO THIS VAR?
			###self._errors["abbrev"] = self.error_class(
				###["Abbreviation already used."])

		return clean_data

###REREAD TO PROVE USEFUL?
def collect_CG_entries(lab_group, overwrite=False):
	compound_guide = get_cache(lab_group, "COMPOUNDGUIDE")
	if not compound_guide or overwrite:
		compound_guide = CompoundEntry.objects.filter(lab_group=lab_group).order_by("compound")
		set_cache(lab_group, "COMPOUNDGUIDE", list(compound_guide))
	return compound_guide

def collect_CG_name_pairs(lab_group, overwrite=False):
	pairs = get_cache(lab_group, "COMPOUNDGUIDE|NAMEPAIRS")
	if not pairs or overwrite:
		compound_guide = collect_CG_entries(lab_group)
		pairs = {entry.abbrev: entry.compound for entry in compound_guide}
		set_cache(lab_group, "COMPOUNDGUIDE|NAMEPAIRS", pairs)
	return pairs

def new_CG_entry(lab_group, **kwargs): ###Not re-read yet.
	try:
		new_entry = CompoundEntry()
		#Set the self-assigning fields:
		setattr(new_entry, "lab_group", lab_group)

		#Set the non-user field values.
		for (field, value) in kwargs.items(): #Assume data passed to the function is clean.
			setattr(new_entry, field, value)
		return new_entry
	except Exception as e:
		raise Exception("CompoundEntry construction failed!")

############### DATA ENTRY ########################
calc_fields = ['XXXtitle', 'XXXinorg1', 'XXXinorg1mass', 'XXXinorg1moles', 'XXXinorg2', 'XXXinorg2mass',
			'XXXinorg2moles', 'XXXinorg3', 'XXXinorg3mass','XXXinorg3moles', 'XXXorg1', 'XXXorg1mass',
			'XXXorg1moles', 'XXXorg2', 'XXXorg2mass', 'XXXorg2moles', 'XXXoxlike1', 'XXXoxlike1mass',
			'XXXoxlike1moles', 'Temp_max', 'time', 'slowCool', 'pH',
			'leak', 'numberInorg', 'numberOrg', 'numberOxlike', 'numberComponents', 'inorgavgpolMax',
			'inorgrefractivityMax', 'inorgmaximalprojectionareaMax', 'inorgmaximalprojectionradiusMax',
			'inorgmaximalprojectionsizeMax', 'inorgminimalprojectionareaMax', 'inorgminimalprojectionradiusMax',
			'inorgminimalprojectionsizeMax', 'inorgavgpol_pHdependentMax',
			'inorgmolpolMax', 'inorgvanderwaalsMax', 'inorgASAMax',
			'inorgASA+Max', 'inorgASA-Max', 'inorgASA_HMax',
			'inorgASA_PMax', 'inorgpolarsurfaceareaMax', 'inorghbdamsaccMax', 'inorghbdamsdonMax',
			'inorgavgpolMin', 'inorgrefractivityMin', 'inorgmaximalprojectionareaMin',
			'inorgmaximalprojectionradiusMin', 'inorgmaximalprojectionsizeMin',
			'inorgminimalprojectionareaMin', 'inorgminimalprojectionradiusMin',
			'inorgminimalprojectionsizeMin', 'inorgavgpol_pHdependentMin',
			'inorgmolpolMin', 'inorgvanderwaalsMin', 'inorgASAMin',
			'inorgASA+Min', 'inorgASA-Min', 'inorgASA_HMin',
			'inorgASA_PMin', 'inorgpolarsurfaceareaMin', 'inorghbdamsaccMin', 'inorghbdamsdonMin',
			'inorgavgpolArithAvg', 'inorgrefractivityArithAvg', 'inorgmaximalprojectionareaArithAvg',
			'inorgmaximalprojectionradiusArithAvg', 'inorgmaximalprojectionsizeArithAvg',
			'inorgminimalprojectionareaArithAvg', 'inorgminimalprojectionradiusArithAvg',
			'inorgminimalprojectionsizeArithAvg',
			'inorgavgpol_pHdependentArithAvg', 'inorgmolpolArithAvg',
			'inorgvanderwaalsArithAvg', 'inorgASAArithAvg',
			'inorgASA+ArithAvg', 'inorgASA-ArithAvg',
			'inorgASA_HArithAvg', 'inorgASA_PArithAvg',
			'inorgpolarsurfaceareaArithAvg',
			'inorghbdamsaccArithAvg', 'inorghbdamsdonArithAvg',
			'inorgavgpolGeomAvg', 'inorgrefractivityGeomAvg',
			'inorgmaximalprojectionareaGeomAvg', 'inorgmaximalprojectionradiusGeomAvg',
			'inorgmaximalprojectionsizeGeomAvg', 'inorgminimalprojectionareaGeomAvg',
			'inorgminimalprojectionradiusGeomAvg', 'inorgminimalprojectionsizeGeomAvg',
			'inorgavgpol_pHdependentGeomAvg', 'inorgmolpolGeomAvg', 'inorgvanderwaalsGeomAvg',
			'inorgASAGeomAvg', 'inorgASA+GeomAvg', 'inorgASA-GeomAvg', 'inorgASA_HGeomAvg',
			'inorgASA_PGeomAvg', 'inorgpolarsurfaceareaGeomAvg', 'inorghbdamsaccGeomAvg', 'inorghbdamsdonGeomAvg',
			'orgavgpolMax', 'orgrefractivityMax',
			'orgmaximalprojectionareaMax', 'orgmaximalprojectionradiusMax', 'orgmaximalprojectionsizeMax',
			'orgminimalprojectionareaMax', 'orgminimalprojectionradiusMax', 'orgminimalprojectionsizeMax',
			'orgavgpol_pHdependentMax', 'orgmolpolMax',
			'orgvanderwaalsMax', 'orgASAMax', 'orgASA+Max', 'orgASA-Max', 'orgASA_HMax', 'orgASA_PMax',
			'orgpolarsurfaceareaMax', 'orghbdamsaccMax',
			'orghbdamsdonMax', 'orgavgpolMin', 'orgrefractivityMin',
			'orgmaximalprojectionareaMin', 'orgmaximalprojectionradiusMin', 'orgmaximalprojectionsizeMin',
			'orgminimalprojectionareaMin', 'orgminimalprojectionradiusMin',
			'orgminimalprojectionsizeMin', 'orgavgpol_pHdependentMin',
			'orgmolpolMin', 'orgvanderwaalsMin', 'orgASAMin',
			'orgASA+Min', 'orgASA-Min', 'orgASA_HMin', 'orgASA_PMin',
			'orgpolarsurfaceareaMin', 'orghbdamsaccMin',
			'orghbdamsdonMin', 'orgavgpolArithAvg', 'orgrefractivityArithAvg',
			'orgmaximalprojectionareaArithAvg', 'orgmaximalprojectionradiusArithAvg',
			'orgmaximalprojectionsizeArithAvg', 'orgminimalprojectionareaArithAvg',
			'orgminimalprojectionradiusArithAvg', 'orgminimalprojectionsizeArithAvg',
			'orgavgpol_pHdependentArithAvg', 'orgmolpolArithAvg', 'orgvanderwaalsArithAvg',
			'orgASAArithAvg', 'orgASA+ArithAvg', 'orgASA-ArithAvg', 'orgASA_HArithAvg', 'orgASA_PArithAvg',
			'orgpolarsurfaceareaArithAvg', 'orghbdamsaccArithAvg',
			'orghbdamsdonArithAvg', 'orgavgpolGeomAvg', 'orgrefractivityGeomAvg',
			'orgmaximalprojectionareaGeomAvg', 'orgmaximalprojectionradiusGeomAvg',
			'orgmaximalprojectionsizeGeomAvg', 'orgminimalprojectionareaGeomAvg',
			'orgminimalprojectionradiusGeomAvg', 'orgminimalprojectionsizeGeomAvg',
			'orgavgpol_pHdependentGeomAvg', 'orgmolpolGeomAvg', 'orgvanderwaalsGeomAvg',
			'orgASAGeomAvg', 'orgASA+GeomAvg', 'orgASA-GeomAvg',
			'orgASA_HGeomAvg', 'orgASA_PGeomAvg', 'orgpolarsurfaceareaGeomAvg', 'orghbdamsaccGeomAvg',
			'orghbdamsdonGeomAvg', 'oxlikeavgpolMax',
			'oxlikerefractivityMax', 'oxlikemaximalprojectionareaMax',
			'oxlikemaximalprojectionradiusMax', 'oxlikemaximalprojectionsizeMax', 'oxlikeminimalprojectionareaMax',
			'oxlikeminimalprojectionradiusMax', 'oxlikeminimalprojectionsizeMax',
			'oxlikeavgpol_pHdependentMax', 'oxlikemolpolMax',
			'oxlikevanderwaalsMax', 'oxlikeASAMax', 'oxlikeASA+Max',
			'oxlikeASA-Max', 'oxlikeASA_HMax', 'oxlikeASA_PMax',
			'oxlikepolarsurfaceareaMax', 'oxlikehbdamsaccMax',
			'oxlikehbdamsdonMax', 'oxlikeavgpolMin',
			'oxlikerefractivityMin', 'oxlikemaximalprojectionareaMin',
			'oxlikemaximalprojectionradiusMin', 'oxlikemaximalprojectionsizeMin',
			'oxlikeminimalprojectionareaMin', 'oxlikeminimalprojectionradiusMin',
			'oxlikeminimalprojectionsizeMin', 'oxlikeavgpol_pHdependentMin', 'oxlikemolpolMin',
			'oxlikevanderwaalsMin', 'oxlikeASAMin', 'oxlikeASA+Min',
			'oxlikeASA-Min', 'oxlikeASA_HMin', 'oxlikeASA_PMin',
			'oxlikepolarsurfaceareaMin', 'oxlikehbdamsaccMin',
			'oxlikehbdamsdonMin', 'oxlikeavgpolArithAvg',
			'oxlikerefractivityArithAvg', 'oxlikemaximalprojectionareaArithAvg',
			'oxlikemaximalprojectionradiusArithAvg', 'oxlikemaximalprojectionsizeArithAvg', 'oxlikeminimalprojectionareaArithAvg',
			'oxlikeminimalprojectionradiusArithAvg', 'oxlikeminimalprojectionsizeArithAvg', 'oxlikeavgpol_pHdependentArithAvg',
			'oxlikemolpolArithAvg', 'oxlikevanderwaalsArithAvg',
			'oxlikeASAArithAvg', 'oxlikeASA+ArithAvg',
			'oxlikeASA-ArithAvg', 'oxlikeASA_HArithAvg',
			'oxlikeASA_PArithAvg', 'oxlikepolarsurfaceareaArithAvg',
			'oxlikehbdamsaccArithAvg', 'oxlikehbdamsdonArithAvg',
			'oxlikeavgpolGeomAvg', 'oxlikerefractivityGeomAvg',
			'oxlikemaximalprojectionareaGeomAvg', 'oxlikemaximalprojectionradiusGeomAvg', 'oxlikemaximalprojectionsizeGeomAvg',
			'oxlikeminimalprojectionareaGeomAvg', 'oxlikeminimalprojectionradiusGeomAvg', 'oxlikeminimalprojectionsizeGeomAvg',
			'oxlikeavgpol_pHdependentGeomAvg', 'oxlikemolpolGeomAvg',
			'oxlikevanderwaalsGeomAvg', 'oxlikeASAGeomAvg',
			'oxlikeASA+GeomAvg', 'oxlikeASA-GeomAvg', 'oxlikeASA_HGeomAvg', 'oxlikeASA_PGeomAvg',
			'oxlikepolarsurfaceareaGeomAvg', 'oxlikehbdamsaccGeomAvg',
			'oxlikehbdamsdonGeomAvg', 'inorg-water-moleratio', 'inorgacc-waterdonratio', 'inorgdon-wateraccratio',
			'org-water-moleratio', 'orgacc-waterdonratio', 'orgdon-wateraccratio', 'inorg-org-moleratio',
			'inorgacc-orgdonratio', 'inorgdon-orgaccratio', 'notwater-water-moleratio', 'notwateracc-waterdonratio',
			'notwaterdon-wateraccratio', 'purity', 'outcome']

class DataCalc(models.Model):
	for calc_field in calc_fields:
		#Make sure field names don't contain operators.
		calc_field = calc_field.replace("+","PLUS").replace("-","MINUS")
		exec("{0} = models.CharField(\"{0}\", max_length=22)".format(calc_field))

	def __unicode__(self):
		return u"{}".format(self.XXXtitle);


#Create the form choices from the pre-defined ranges.
OUTCOME_CHOICES = [[opt,opt] for opt in edit_choices["outcomeChoices"]]
PURITY_CHOICES = [[opt,opt] for opt in edit_choices["purityChoices"]]
UNIT_CHOICES = [[opt,opt] for opt in edit_choices["unitChoices"]]
BOOL_CHOICES = [[opt,opt] for opt in edit_choices["boolChoices"]]

#Fields that are allowed to be stored as listy_strings.
list_fields = ["reactant", "quantity", "unit"]

#Many data are saved per lab group. Each data represents one submission.
class Data(models.Model):
	#List Fields
	for i in CONFIG.reactant_range():
		exec("reactant_{0} = models.CharField(\"Reactant {0}\", max_length=30)".format(i))
		exec("quantity_{0} = models.CharField(\"Quantity {0}\", max_length=10)".format(i))
		exec("unit_{0} = models.CharField(\"Unit {0}\", max_length=4)".format(i))

	ref = models.CharField("Reference", max_length=12)
	temp = models.CharField("Temperature", max_length=10)
	time = models.CharField("Time", max_length=10) ###
	pH = models.CharField("pH", max_length=5)

	#Yes/No/? Fields:
	slow_cool = models.CharField("Slow Cool", max_length=10)
	leak = models.CharField("Leak", max_length=10)
	outcome = models.CharField("Outcome", max_length=1)
	purity = models.CharField("Purity", max_length=1)

	notes = models.CharField("Notes", max_length=200, blank=True)

	#Self-assigning Fields:
	calculations = models.ForeignKey(DataCalc, unique=False, blank=True, null=True)
	user = models.ForeignKey(User, unique=False)
	lab_group = models.ForeignKey(Lab_Group, unique=False)
	creation_time = models.CharField("Created", max_length=26, null=True, blank=True)
	is_valid = models.BooleanField()

	#Categorizing Fields:
	duplicate_of = models.CharField("Duplicate", max_length=12, null=True, blank=True)
	recommended = models.CharField("Recommended", max_length=10)

	def __unicode__(self):
		return u"{} -- (LAB: {})".format(self.ref, self.lab_group.lab_title)

def validate_name(abbrev_to_check, lab_group):
	#Get the cached set of abbreviations.
	abbrevs = collect_CG_name_pairs(lab_group)
	return abbrev_to_check in abbrevs

#Add specified entries to a datum. Assume fields are now valid.
def new_Data_entry(user, **kwargs): ###Not re-read yet.
	try:
		new_entry = Data()
		#Set the self-assigning fields:
		setattr(new_entry, "creation_time", str(datetime.datetime.now()))
		setattr(new_entry, "user", user)
		setattr(new_entry, "lab_group", user.get_profile().lab_group)

		#Set the non-user field values.
		for (field, value) in kwargs.items(): #Assume data passed to the function is clean.
			setattr(new_entry, field, value)
		return new_entry
	except Exception as e:
		raise Exception("Data construction failed!")

def get_model_field_names(both=False, verbose=False, model="Data", unique_only=False):
	clean_fields = []

	if model=="Data":
		fields_to_ignore = {u"id","user","lab_group", "creation_time", "calculations", "is_valid"}
		dirty_fields = [field for field in Data._meta.fields if field.name not in fields_to_ignore]
	elif model=="CompoundEntry":
		fields_to_ignore = {u"id","lab_group"} ###Auto-populate?
		dirty_fields = [field for field in CompoundEntry._meta.fields if field.name not in fields_to_ignore]
	else:
		raise Exception("Unknown model specified.")

	#Ignore any field that is in fields_to_ignore.
	for field in dirty_fields:
		#Return the non list-fields:
		if unique_only and field.name[-1].isdigit(): continue

		#Return either the verbose names or the non-verbose names.
		if both:
			clean_fields += [{"verbose":field.verbose_name, "raw":field.name}] ###Make verbose names pretty
		elif verbose:
			clean_fields += [field.verbose_name] ###Make verbose names pretty
		else:
			clean_fields += [field.name]
	return clean_fields

def get_ref_set(lab_group):
	ref_set = get_cache(lab_group, "REFS")
	if not ref_set:
		ref_set = set(Data.objects.values_list('ref', flat=True))
		set_cache(lab_group, "REFS", ref_set)
	return ref_set

def revalidate_data(data, lab_group, batch=False):
	#Collect the data to validate
	dirty_data = {field:getattr(data, field) for field in get_model_field_names()}
	#Validate and collect any errors
	(clean_data, errors) = full_validation(dirty_data, lab_group)

	if errors:###
		missing = []
		for i in xrange(1,6):
			if errors.get("reactant_{}".format(i)):
				missing.append(getattr(data, "reactant_{}".format(i)).encode('ascii','ignore'))

		if missing:
			reaction = getattr(data, "reactant_1")
			for i in xrange(2,6):
				reactant = getattr(data, "reactant_{}".format(i))
				if reactant:
					reaction +=  " + {}".format(reactant)
			return ("{0} ({1})\n\tMissing:{2}\n".format(reaction, data.ref, missing), missing)

	return ("",None)

	is_valid = False if errors else True
	setattr(data, "is_valid", is_valid)
	data.save()
	#Does not auto-clear the cache --only modifies the data entry.

def full_validation(dirty_data, lab_group):
	parsed_data = {} #Data that needs to be checked.
	clean_data = {} #Keep track of cleaned fields
	errors = {}

	fields = get_model_field_names()

	#Gather the "coupled" fields (ie, the fields ending in a similar number)
	for field in list_fields:
		exec("{} = [[]]*{}".format(field, CONFIG.num_reactants)) #### {field: [[]]*CONFIG.num_reactants for field in list_fields} {field:
		parsed_data[field] = [[]]*CONFIG.num_reactants
		clean_data[field] = []
	###fields = {field: [[]]*CONFIG.num_reactants for field in list_fields} ###CHANGE INTO ME, Future Casey
	###parsed_data = {field: [[]]*CONFIG.num_reactants for field in list_fields}
	###clean_data = {field: [] for field in list_fields}

	#Visible fields that are not required (not including rxn info).
	not_required = { ###Auto-generate?
		"notes", "duplicate_of"
	}

	for field in dirty_data:
		if field[-1].isdigit():
			#Put the data in its respective list.
			rel_list = eval("{}".format(field[:-2]))
			rel_list[int(field[-1])-1] = (dirty_data[field])
		else:
			try:
				assert(dirty_data[field]) #Assert that data was entered.
				parsed_data[field] = dirty_data[field]
			except:
				if field in not_required:
					clean_data[field] = "" #If nothing was entered, store nothing ###Used to be "?" -- why?
				else:
					errors[field] = "Field required."

	#Check that equal numbers of fields are present in each list
	for i in xrange(CONFIG.num_reactants):
		x = 0
		if reactant[i]:
			x+=2
			parsed_data["reactant"][i] = reactant[i]
		if quantity[i]:
			x+=3
			parsed_data["quantity"][i] = quantity[i]
		parsed_data["unit"][i] = unit[i] #Menu, so no reason to check in form.

		#Unit is added automatically, so don't check it.
		if x == 3:
			errors["reactant_"+str(i+1)] = "Info missing."
		elif x == 2:
			errors["quantity_"+str(i+1)] = "Info missing."

	for field in parsed_data:
		#Make sure each reactant name is valid.
		if field=="reactant":
			for i in xrange(len(parsed_data[field])):
				if not parsed_data[field][i]: continue #Don't validate empty values.
				try:
					dirty_datum = str(parsed_data[field][i])
					assert(validate_name(dirty_datum, lab_group))
					clean_data["{}_{}".format(field,i+1)] = dirty_datum #Add the filtered value to the clean values dict.
				except:
					errors["{}_{}".format(field,i+1)] = "Not in compound guide!"

		#Numeric fields:
		elif field in float_fields or field in int_fields:
			if field in float_fields: field_type="float"
			else: field_type="int"

			if field in list_fields:
				for i in xrange(len(parsed_data[field])):
					if not parsed_data[field][i]: continue #Don't validate empty values.
					try:
						dirty_datum = eval("{}(parsed_data[field][i])".format(field_type))
						assert(quick_validation(field, dirty_datum))
						clean_data["{}_{}".format(field,i+1)] = dirty_datum
					except:
						errors["{}_{}".format(field,i+1)] = "Must be between {} and {}.".format(data_ranges[field][0], data_ranges[field][1])
			else:
				try:
					dirty_datum = eval("{}(parsed_data[field])".format(field_type))
					assert(quick_validation(field, dirty_datum))
					parsed_data[field] = dirty_datum #Add the filtered mass to clean_data
					clean_data[field] = parsed_data[field]
				except:
					errors[field] = "Must be between {} and {}.".format(data_ranges[field][0], data_ranges[field][1])

		#Option fields:
		elif field in opt_fields:
			if field in list_fields:
				for i in xrange(len(parsed_data[field])):
					if not parsed_data[field][i]: continue #Don't validate empty values.
					try:
						dirty_datum = str(parsed_data[field][i])
						assert(quick_validation(field, dirty_datum))
						clean_data["{}_{}".format(field,i+1)] = dirty_datum
					except:
						if field in bool_fields:
							category="boolChoices"
						else:
							category = field+"Choices"

						errors["{}_{}".format(field,i+1)] = "Field must be one of: {}".format(edit_choices[category])
			else:
				try:
					dirty_datum = str(parsed_data[field])
					assert(quick_validation(field, dirty_datum))
					clean_data[field] = dirty_datum
				except:
					if field in bool_fields:
						category="boolChoices"
					else:
						category = field+"Choices"

					errors[field] = "Field must be one of: {}".format(edit_choices[category])

		#Text fields.
		elif field in {"ref","notes", "duplicate_of"}: ###No repeats in ref
			try:
				dirty_datum = str(parsed_data[field])
				assert(quick_validation(field, dirty_datum))

				#Check to make sure no references are repeated.
				if field=="ref":
					try:
						#Gather the reference_set to make sure references are unique.
						ref_set = get_ref_set(lab_group)
						print "CHECKING!"

						#Check to make sure the ref isn't in the ref_set.
						assert(not dirty_datum in ref_set)
						clean_data[field] = dirty_datum
					except:
						errors[field] = "Already in use."

				elif field=="duplicate_of":
					try:
						#Gather the reference_set to make sure references are unique.
						ref_set = get_ref_set(lab_group)

						#Check to make sure the ref isn't in the ref_set.
						assert(dirty_datum in ref_set)
						clean_data[field] = dirty_datum
					except:
						errors[field] = "Nonexistent reference."
				else:
					clean_data[field] = dirty_datum
			except:
				errors[field] = "Cannot exceed {} characters.".format(data_ranges[field][1])

	return (clean_data, errors)

class DataEntryForm(ModelForm):
	#List Fields
	for i in CONFIG.reactant_range():
		if i > 2:
			required="required=False,"
		else:
			required=""
		exec("reactant_{0} = CharField({1} label='Reactant {0}', widget=TextInput(".format(i, required) +
			"attrs={'class':'form_text autocomplete_reactant',"+
			"'title':'Enter the name of the reactant.'}))")
		exec("quantity_{0} = CharField({1} label='Quantity {0}', widget=TextInput(".format(i, required) +
			"attrs={'class':'form_text form_text_short', 'placeholder':'Amount',"+
			"'title':'Enter the amount of reactant.'}))")
		exec("unit_{0} = ChoiceField(choices = UNIT_CHOICES, widget=Select(".format(i, required) +
			"attrs={'class':'form_text dropDownMenu',"+
			"'title':'\"g\": gram <br/> \"mL\": milliliter <br/> \"d\": drop'}))")
	ref = CharField(label="Ref.", widget=TextInput(
		attrs={'class':'form_text form_text_short',
		"title":"The lab notebook and page number where the data can be found."}))
	temp = CharField(label="Temp.", widget=TextInput(
		attrs={'class':'form_text form_text_short', 'placeholder':'Celsius',
		"title":"The temperature at which the reaction took place."}))
	time = CharField(widget=TextInput(
		attrs={'class':'form_text form_text_short', 'placeholder':'Hours',
		"title":"How long the reaction was allowed to occur."})) ###
	pH = CharField(label="pH", widget=TextInput(
		attrs={'class':'form_text form_text_short', 'placeholder':'0 - 14',
		"title":"The pH at which the reaction occurred."}))
	slow_cool = ChoiceField(label="Slow Cool", choices = BOOL_CHOICES,
		widget=Select(attrs={'class':'form_text dropDownMenu',
		"title":"Was the reaction allowed to slow-cool?"}))
	leak = ChoiceField(choices = BOOL_CHOICES, widget=Select(
		attrs={'class':'form_text dropDownMenu',
		"title":"Was a leak present during the reaction?"}))
	outcome = ChoiceField(choices = OUTCOME_CHOICES, widget=Select(
		attrs={'class':'form_text dropDownMenu',
		"title":"0: No Data Available <br/> 1: No Solid<br/> 2: Noncrystalline/Brown<br/>3: Powder/Crystallites<br/>4: Large Single Crystals"}))
	purity = ChoiceField(choices = PURITY_CHOICES, widget=Select(
		attrs={'class':'form_text dropDownMenu',
		"title":"0: No Data Available<br/> 1: Multiphase<br/> 2: Single Phase"}))
	notes = CharField(required = False, widget=TextInput(
		attrs={'class':'form_text form_text_long',
		"title":"Additional notes about the reaction."}))

	duplicate_of = CharField(required = False,
		label="Duplicate of", widget=TextInput(
		attrs={'class':'form_text form_text_short',
		"title":"The reaction reference of which this data is a duplicate."}))
	recommended = ChoiceField(choices = BOOL_CHOICES, widget=Select(
		attrs={'class':'form_text dropDownMenu',
		"title":"Did we recommend this reaction to you?"}))

	class Meta:
		model = Data
		exclude = ("user","lab_group", "creation_time")
		#Set the field order.
		fields = [
			"reactant_1", "quantity_1", "unit_1",
			"reactant_2", "quantity_2", "unit_2",
			"reactant_3", "quantity_3", "unit_3",
			"reactant_4", "quantity_4", "unit_4",
			"reactant_5", "quantity_5", "unit_5",
			"ref", "temp", "time", "pH", "slow_cool",
			"leak", "outcome", "purity",
			"duplicate_of", "recommended","notes"
		]

	def __init__(self, user=None, *args, **kwargs):
		###http://stackoverflow.com/questions/1202839/get-request-data-in-django-form
		super(DataEntryForm, self).__init__(*args, **kwargs)

		if user:
			self.user = user
			self.lab_group = user.get_profile().lab_group
		self.creation_time = str(datetime.datetime.now())

	def save(self, commit=True):
		datum = super(DataEntryForm, self).save(commit=False)
		datum.user = self.user
		datum.lab_group = self.lab_group
		datum.creation_time = self.creation_time
		datum.is_valid = True #If validation succeeded and data is saved, then it is_valid.

		if commit:
			datum.save()
		return datum


	#Clean the data that is input using the form.
	def clean(self):
		#Initialize the variables needed for the cleansing process.
		dirty_data = super(DataEntryForm, self).clean() #Get the available raw (dirty) data

		#Gather the clean_data and any errors found.
		clean_data, gathered_errors = full_validation(dirty_data, self.lab_group)
		form_errors = {field: self.error_class([message]) for (field, message) in gathered_errors.iteritems()}

		#Apply the errors to the form.
		self._errors.update(form_errors)

		#Add the non-input information to the clean data package:
		clean_data["lab_group"] = self.lab_group
		clean_data["user"] = self.user
		clean_data["creation_time"] = self.creation_time

		return clean_data