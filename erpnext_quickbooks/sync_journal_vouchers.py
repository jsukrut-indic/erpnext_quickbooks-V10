from __future__ import unicode_literals
import frappe
from frappe import _
import requests.exceptions
from .utils import make_quickbooks_log
import datetime


def sync_entry(quickbooks_obj):
	"""Fetch JournalEntry data from QuickBooks"""
	# print "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n"
	# print "________c___quickbooks_obj for sync_si_payment_______________________________________________________________" 
	Entry = """SELECT count(*) from JournalEntry""" 
	qb_Entry = quickbooks_obj.query(TxnId)
	if qb_Entry['QueryResponse']:
		get_qb_Entry =  qb_Entry['QueryResponse']['JournalEntry']
		# print get_qb_Entry , "-----------------"
		sync_journal_entries(get_qb_Entry)

def sync_journal_entries(get_qb_Entry):
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	for qb_journal_entry in get_qb_Entry:
		if qb_journal_entry.get('Id') == "5886":
			create_journal_entry(qb_journal_entry, quickbooks_settings)

def create_journal_entry(qb_journal_entry, quickbooks_settings, quickbooks_journal_entry_list=[]):
	""" store JournalEntry data in ERPNEXT """ 
	journal = None
	qb_journal_entry_id = ''
	if qb_journal_entry.get('Id'):
		qb_journal_entry_id = "JE" + qb_journal_entry.get('Id')
	try:	
		if not 	frappe.db.get_value("Journal Entry", {"quickbooks_journal_entry_id": qb_journal_entry_id}, "name"): 
			journal = frappe.new_doc("Journal Entry")
			journal.quickbooks_journal_entry_id = qb_journal_entry_id
			journal.voucher_type = _("Journal Entry")
			journal.naming_series = "JE-Quickbooks-"
			journal.posting_date = qb_journal_entry.get('TxnDate')
			journal.multi_currency = 1
			get_journal_entry_accounts(journal, qb_journal_entry, quickbooks_settings)
			journal.flags.validate = False
			journal.flags.ignore_mandatory = True
			journal.save()
			journal.submit()
			frappe.db.commit()
			quickbooks_journal_entry_list.append(journal.quickbooks_journal_entry_id)

	except Exception, e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_quickbooks_log(title=e.message, status="Error", method="create_journal_entry", message=frappe.get_traceback(),
				request_data=qb_journal_entry, exception=True)
	
	return quickbooks_journal_entry_list

def get_journal_entry_accounts(journal, qb_journal_entry, quickbooks_settings):
	def append_row(row, debit_in_account_currency, credit_in_account_currency):
		if debit_in_account_currency:
			debit_credit_entry(debit_in_account_currency)
		if credit_in_account_currency:
			debit_credit_entry(credit_in_account_currency)

	def debit_credit_entry(entries):
		account = journal.append("accounts", {})
		account.account = entries.get('account')
		account.party_type = entries.get('party_type')
		account.party = entries.get('party')
		account.exchange_rate = entries.get('exchange_rate')
		account.debit_in_account_currency = entries.get('final_amt') if entries.get('posting_type') == 'Debit' else None
		account.credit_in_account_currency = entries.get('final_amt') if entries.get('posting_type') == 'Credit' else None
	journal.set("accounts", [])

	for row in qb_journal_entry['Line']:
		if row.get('JournalEntryLineDetail').get('PostingType') == 'Debit':
			debit_in_account_currency = get_debit_in_account_currency(row, qb_journal_entry)
			credit_in_account_currency = {}
				
		if row.get('JournalEntryLineDetail').get('PostingType') == 'Credit':
			debit_in_account_currency = {}
			credit_in_account_currency = get_credit_in_account_currency(row, qb_journal_entry)
		append_row(row, debit_in_account_currency, credit_in_account_currency)
		
		TaxAmount =row['JournalEntryLineDetail'].get('TaxAmount')
		if TaxAmount:
			debit_in_account_currency = get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, "Debit") if row['JournalEntryLineDetail']['PostingType'] == "Debit" else None
			credit_in_account_currency = get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, "Credit") if row['JournalEntryLineDetail']['PostingType'] == "Credit" else None
			append_row(row, debit_in_account_currency, credit_in_account_currency)
	
# def get_Account(row):
# 	quickbooks_account_reference = row.get('JournalEntryLineDetail')['AccountRef']['value']
# 	return frappe.db.get_value("Account", {"quickbooks_account_id": quickbooks_account_reference}, "name")
	

def get_party_type(row):
	quickbooks_party_type = row.get('JournalEntryLineDetail').get('Entity').get('Type') if row.get('JournalEntryLineDetail').get('Entity') else ''
	
	if quickbooks_party_type == "Customer":
		return "Customer"
	elif quickbooks_party_type == "Vendor":
		return "Supplier"
	elif quickbooks_party_type == "Employee":
		return "Employee"
	else:
		return quickbooks_party_type


	# if quickbooks_party_type == "Customer":
	# 	return "Customer"
	# elif quickbooks_party_type == "Vendor":
	# 	return "Supplier"
	# else:
	# 	return quickbooks_party_type

def get_party(row):
	quickbooks_party_type = row.get('JournalEntryLineDetail').get('Entity').get('Type') if row.get('JournalEntryLineDetail').get('Entity') else ''
	quickbooks_party = row.get('JournalEntryLineDetail').get('Entity').get('EntityRef').get('value') if row.get('JournalEntryLineDetail').get('Entity') else ''
	if quickbooks_party_type == "Customer" and quickbooks_party:
		return frappe.db.get_value("Customer", {"quickbooks_cust_id": quickbooks_party}, "name")
	elif quickbooks_party_type == "Vendor" and quickbooks_party:
		return frappe.db.get_value("Supplier", {"quickbooks_supp_id": quickbooks_party}, "name")
	else:
		return quickbooks_party 

def get_debit_in_account_currency(row, qb_journal_entry):
	posting_type = row.get('JournalEntryLineDetail').get('PostingType')
	total_amt = row.get('Amount') if row['JournalEntryLineDetail']['PostingType'] == "Debit" else None
	return get_account_currency(qb_journal_entry, row, total_amt, posting_type) if total_amt else None

def get_credit_in_account_currency(row, qb_journal_entry):
	posting_type = row.get('JournalEntryLineDetail').get('PostingType')
	total_amt = row.get('Amount') if posting_type == "Credit" else None
	return get_account_currency(qb_journal_entry, row, total_amt, posting_type) if total_amt else None

def get_account_currency(qb_journal_entry, row, total_amt, posting_type):
	account_details ={}
	account_details['posting_type'] = posting_type
	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
	quickbooks_account_reference = row.get('JournalEntryLineDetail').get('AccountRef').get('value')
	account_detail_info = get_jv_account_detail(quickbooks_account_reference)
	account_details['account'] = account_detail_info.get('name')
	party = "QB Supplier"
	party_type ="Supplier"
	# party, party_type = get_party("Sukrut"), get_party_type("Customer")

	
	if party and party_type:
		account_details['party'] = party 
		account_details['party_type'] = party_type

	if account_detail_info.get('account_currency') == company_currency:
		account_details['exchange_rate'] = 1
		account_details['final_amt'] = total_amt * 1
		# account_details['final_amt'] = total_amt * qb_journal_entry.get('ExchangeRate')
		return account_details
	else:
		account_details['exchange_rate'] = qb_journal_entry.get('ExchangeRate')
		account_details['final_amt'] = total_amt
		return account_details

def get_jv_account_detail(quickbooks_account_reference):
	return frappe.db.get_value("Account", {"quickbooks_account_id": quickbooks_account_reference}, ["name", "account_currency"], as_dict=1)

def get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, posting_type):
	account_details ={}
	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
	account_detail_info = get_tax_head(row, qb_journal_entry, quickbooks_settings)
	account_details['account'] = account_detail_info.get('name')
	account_details['posting_type'] = posting_type
	
	if account_detail_info.get('account_currency') == company_currency:
		account_details['exchange_rate'] = 1
		account_details['final_amt'] = row['JournalEntryLineDetail'].get('TaxAmount') * qb_journal_entry.get('ExchangeRate')
		return account_details
	else:
		account_details['exchange_rate'] = qb_journal_entry.get('ExchangeRate')
		account_details['final_amt'] = row['JournalEntryLineDetail'].get('TaxAmount')
		return account_details

def get_tax_head(row, qb_journal_entry, quickbooks_settings):
	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
	tax_code_ref = row.get('JournalEntryLineDetail').get('TaxCodeRef')
	tax_head = ''
	if tax_code_ref and not tax_code_ref.get('value') == 'NON':
		if row.get('JournalEntryLineDetail').get('TaxApplicableOn') == "Sales":
			condition = "(select * from `tabQuickBooks SalesTaxRateList` where parent = {0}) as qbs " .format(tax_code_ref.get('value'))
		elif row.get('JournalEntryLineDetail').get('TaxApplicableOn') == "Purchase":
			condition = "(select * from `tabQuickBooks PurchaseTaxRateList` where parent = {0}) as qbs" .format(tax_code_ref.get('value')) 
		query = """select 
					qbr.name, qbr.display_name as tax_head, qbr.rate_value as tax_percent
				from
					`tabQuickBooks TaxRate` as qbr, {0}
				where
					qbr.tax_rate_id = qbs.tax_rate_id """.format(condition)
		individual_item_tax =  frappe.db.sql(query, as_dict=1)	
		tax_head = individual_item_tax[0]['tax_head']
	tax_account = get_tax_head_mapped_to_particular_account(tax_head, quickbooks_settings)
	return tax_account

def get_tax_head_mapped_to_particular_account(tax_head, quickbooks_settings):

	""" fetch respective tax head from Tax Head Mappe table """
	account_head_erpnext =frappe.db.get_value("Tax Head Mapper", {"tax_head_quickbooks": tax_head, \
			"parent": "Quickbooks Settings"}, "account_head_erpnext")
	if not account_head_erpnext:
		account_head_erpnext = quickbooks_settings.undefined_tax_account
	account_head_erpnext = frappe.db.get_value("Account", {"name": account_head_erpnext}, ["name", "account_currency"], as_dict=1)
	return account_head_erpnext

