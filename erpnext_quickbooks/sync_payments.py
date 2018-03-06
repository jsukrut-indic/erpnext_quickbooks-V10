from __future__ import unicode_literals
import frappe
from frappe import _
import json
from frappe.utils import flt, cstr, nowdate
import requests.exceptions
from .utils import make_quickbooks_log, pagination
from pyqb.quickbooks.batch import batch_create, batch_delete
from frappe.utils import nowdate

"""Sync all the Sales Invoice Payments from Quickbooks to ERPNEXT"""
def sync_payments(quickbooks_obj): 
	"""Fetch payment data from QuickBooks"""
	quickbooks_invoice_list = []
	quickbooks_payment_list = []  
	business_objects = "Payment"
	get_qb_payments =  pagination(quickbooks_obj, business_objects)
	if get_qb_payments:
		# print " NO Of Payments" ,len(get_qb_payments)
		sync_qb_si_payments(get_qb_payments, quickbooks_invoice_list)

def sync_qb_si_payments(get_qb_payments, quickbooks_payment_list):
	company_name = frappe.defaults.get_defaults().get("company")
	default_currency = frappe.db.get_value("Company" ,{"name":company_name},"default_currency")
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	for qb_payment in get_qb_payments:
		try:
			create_jv_from_qb_payment(qb_payment,quickbooks_settings,quickbooks_payment_list)
		except Exception, e:
			make_quickbooks_log(title=e.message, status="Error", method="sync_qb_si_payments", message=frappe.get_traceback(),
						request_data=qb_payment, exception=True)
			
def create_jv_from_qb_payment(qb_payment,quickbooks_settings,quickbooks_payment_list):
	qb_payment_id = ''
	if qb_payment.get('Id'):
		qb_payment_id = "JE" + qb_payment.get('Id')
	try:	
		if not 	frappe.db.get_value("Journal Entry", {"quickbooks_payment_id": qb_payment_id}, "name"): 
			print " Inprocess for create_jv_from_qb_payment "
			journal = frappe.new_doc("Journal Entry")
			journal.quickbooks_payment_id = qb_payment_id
			journal.voucher_type = _("Journal Entry")
			journal.naming_series = "JE-Quickbooks-"
			journal.posting_date = qb_payment.get('TxnDate')
			journal.multi_currency = 1
			journal.total_debit = qb_payment.get('TotalAmt')
			journal.total_credit =  qb_payment.get('TotalAmt')
			get_journal_entry_accounts(journal, qb_payment, quickbooks_settings)
			# journal.flags.ignore_validate = True
			journal.flags.ignore_mandatory = True
			# print "journal",journal.__dict__
			# print "Account",journal.accounts[0].__dict__
			# print "Account",journal.accounts[1].__dict__
			journal.save()
			print "journal",journal.name
			journal.submit()
			frappe.db.commit()
			quickbooks_payment_list.append(journal.quickbooks_payment_id)
	except Exception, e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_quickbooks_log(title=e.message, status="Error", method="create_jv_from_qb_payment", message=frappe.get_traceback(),
				request_data=qb_payment, exception=True)
	
def get_journal_entry_accounts(journal, qb_payment, quickbooks_settings):
	# print  "journal, qb_journal_entry, quickbooks_settings",journal, qb_journal_entry, quickbooks_settings
	# print " Inprocess for get_journal_entry_accounts "
	debit_entry = credit_entry = 1
	company_name = frappe.defaults.get_defaults().get("company")
	for bill in qb_payment.get('Line'):
		print ":::::::",bill
		si_name = frappe.db.get_value("Sales Invoice", {"quickbooks_invoice_no": bill.get('LineEx').get('any')[2].get('value').get('Value')}, "name")
		print "si_name",si_name
		if si_name:
			debit_to = frappe.db.get_value("Sales Invoice", {"name": si_name}, "debit_to")
			income_account = frappe.db.get_value("Sales Invoice Item", {"parent": si_name}, "income_account")
			if debit_entry:
				default_receivable_account = frappe.db.get_value("Company", {"name": company_name}, "default_receivable_account")
				account = journal.append("accounts", {})
				account.account = income_account
				account.debit_in_account_currency = qb_payment.get('TotalAmt')		
			if credit_entry:
				default_payable_account = frappe.db.get_value("Company", {"name": company_name}, "default_payable_account")
				account = journal.append("accounts", {})
				account.credit_in_account_currency = qb_payment.get('TotalAmt')
				account.account = debit_to
				account.reference_type = "Sales Invoice"
				account.reference_name = si_name
				account.party = qb_payment.get('CustomerRef').get('name')
				account.party_type ="Customer"

	# si_name = frappe.db.get_value("Sales Invoice", {"quickbooks_invoice_no": qb_payment.get('Line')[0].get('LineEx').get('any')[2].get('value').get('Value')}, "name")
	# # print "company_name",company_name
	# # print "si_name",si_name
	# if si_name:
	# 	debit_to = frappe.db.get_value("Sales Invoice", {"name": si_name}, "debit_to")
	# 	income_account = frappe.db.get_value("Sales Invoice Item", {"parent": si_name}, "income_account")
	# 	if debit_entry:
	# 		default_receivable_account = frappe.db.get_value("Company", {"name": company_name}, "default_receivable_account")
	# 		account = journal.append("accounts", {})
	# 		account.account = income_account
	# 		account.debit_in_account_currency = qb_payment.get('TotalAmt')
	# 		account.idx = 1		
	# 	if credit_entry:
	# 		default_payable_account = frappe.db.get_value("Company", {"name": company_name}, "default_payable_account")
	# 		account = journal.append("accounts", {})
	# 		account.credit_in_account_currency = qb_payment.get('TotalAmt')
	# 		account.account = debit_to
	# 		account.reference_type = "Sales Invoice"
	# 		account.reference_name = si_name
	# 		account.party = qb_payment.get('CustomerRef').get('name')
	# 		account.party_type ="Customer"
	# 		account.idx = 2
		

# 	def append_row(row, debit_in_account_currency, credit_in_account_currency):
# 		if debit_in_account_currency:
# 			debit_credit_entry(debit_in_account_currency)
# 		if credit_in_account_currency:
# 			debit_credit_entry(credit_in_account_currency)

# 	def debit_credit_entry(entries):
# 		account = journal.append("accounts", {})
# 		account.account = entries.get('account')
# 		account.party_type = entries.get('party_type')
# 		account.party = entries.get('party')
# 		account.exchange_rate = entries.get('exchange_rate')
# 		account.debit_in_account_currency = entries.get('final_amt') if entries.get('posting_type') == 'Debit' else None
# 		account.credit_in_account_currency = entries.get('final_amt') if entries.get('posting_type') == 'Credit' else None
# 	journal.set("accounts", [])

# 	for row in qb_journal_entry['Line']:
# 		if row.get('JournalEntryLineDetail').get('PostingType') == 'Debit':
# 			debit_in_account_currency = get_debit_in_account_currency(row, qb_journal_entry)
# 			credit_in_account_currency = {}
				
# 		if row.get('JournalEntryLineDetail').get('PostingType') == 'Credit':
# 			debit_in_account_currency = {}
# 			credit_in_account_currency = get_credit_in_account_currency(row, qb_journal_entry)
# 		append_row(row, debit_in_account_currency, credit_in_account_currency)
		
# 		TaxAmount =row['JournalEntryLineDetail'].get('TaxAmount')
# 		if TaxAmount:
# 			debit_in_account_currency = get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, "Debit") if row['JournalEntryLineDetail']['PostingType'] == "Debit" else None
# 			credit_in_account_currency = get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, "Credit") if row['JournalEntryLineDetail']['PostingType'] == "Credit" else None
# 			append_row(row, debit_in_account_currency, credit_in_account_currency)
	
# # def get_Account(row):
# # 	quickbooks_account_reference = row.get('JournalEntryLineDetail')['AccountRef']['value']
# # 	return frappe.db.get_value("Account", {"quickbooks_account_id": quickbooks_account_reference}, "name")
	

# def get_party_type(row):
# 	quickbooks_party_type = row.get('JournalEntryLineDetail').get('Entity').get('Type') if row.get('JournalEntryLineDetail').get('Entity') else ''
	
# 	if quickbooks_party_type == "Customer":
# 		return "Customer"
# 	elif quickbooks_party_type == "Vendor":
# 		return "Supplier"
# 	elif quickbooks_party_type == "Employee":
# 		return "Employee"
# 	else:
# 		return quickbooks_party_type


# 	# if quickbooks_party_type == "Customer":
# 	# 	return "Customer"
# 	# elif quickbooks_party_type == "Vendor":
# 	# 	return "Supplier"
# 	# else:
# 	# 	return quickbooks_party_type

# def get_party(row):
# 	quickbooks_party_type = row.get('JournalEntryLineDetail').get('Entity').get('Type') if row.get('JournalEntryLineDetail').get('Entity') else ''
# 	quickbooks_party = row.get('JournalEntryLineDetail').get('Entity').get('EntityRef').get('value') if row.get('JournalEntryLineDetail').get('Entity') else ''
# 	if quickbooks_party_type == "Customer" and quickbooks_party:
# 		return frappe.db.get_value("Customer", {"quickbooks_cust_id": quickbooks_party}, "name")
# 	elif quickbooks_party_type == "Vendor" and quickbooks_party:
# 		return frappe.db.get_value("Supplier", {"quickbooks_supp_id": quickbooks_party}, "name")
# 	else:
# 		return quickbooks_party 

# def get_debit_in_account_currency(row, qb_journal_entry):
# 	posting_type = row.get('JournalEntryLineDetail').get('PostingType')
# 	total_amt = row.get('Amount') if row['JournalEntryLineDetail']['PostingType'] == "Debit" else None
# 	return get_account_currency(qb_journal_entry, row, total_amt, posting_type) if total_amt else None

# def get_credit_in_account_currency(row, qb_journal_entry):
# 	posting_type = row.get('JournalEntryLineDetail').get('PostingType')
# 	total_amt = row.get('Amount') if posting_type == "Credit" else None
# 	return get_account_currency(qb_journal_entry, row, total_amt, posting_type) if total_amt else None

# def get_account_currency(qb_journal_entry, row, total_amt, posting_type):
# 	account_details ={}
# 	account_details['posting_type'] = posting_type
# 	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
# 	quickbooks_account_reference = row.get('JournalEntryLineDetail').get('AccountRef').get('value')
# 	account_detail_info = get_jv_account_detail(quickbooks_account_reference)
# 	account_details['account'] = account_detail_info.get('name')
# 	party = "QB Supplier"
# 	party_type ="Supplier"
# 	# party, party_type = get_party("Sukrut"), get_party_type("Customer")

	
# 	if party and party_type:
# 		account_details['party'] = party 
# 		account_details['party_type'] = party_type

# 	if account_detail_info.get('account_currency') == company_currency:
# 		account_details['exchange_rate'] = 1
# 		account_details['final_amt'] = total_amt * 1
# 		# account_details['final_amt'] = total_amt * qb_journal_entry.get('ExchangeRate')
# 		return account_details
# 	else:
# 		account_details['exchange_rate'] = qb_journal_entry.get('ExchangeRate')
# 		account_details['final_amt'] = total_amt
# 		return account_details

# def get_jv_account_detail(quickbooks_account_reference):
# 	return frappe.db.get_value("Account", {"quickbooks_account_id": quickbooks_account_reference}, ["name", "account_currency"], as_dict=1)

# def get_jv_tax_entries(row, qb_journal_entry, quickbooks_settings, posting_type):
# 	account_details ={}
# 	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
# 	account_detail_info = get_tax_head(row, qb_journal_entry, quickbooks_settings)
# 	account_details['account'] = account_detail_info.get('name')
# 	account_details['posting_type'] = posting_type
	
# 	if account_detail_info.get('account_currency') == company_currency:
# 		account_details['exchange_rate'] = 1
# 		account_details['final_amt'] = row['JournalEntryLineDetail'].get('TaxAmount') * qb_journal_entry.get('ExchangeRate')
# 		return account_details
# 	else:
# 		account_details['exchange_rate'] = qb_journal_entry.get('ExchangeRate')
# 		account_details['final_amt'] = row['JournalEntryLineDetail'].get('TaxAmount')
# 		return account_details

# def get_tax_head(row, qb_journal_entry, quickbooks_settings):
# 	company_currency = qb_journal_entry.get('CurrencyRef').get('value')
# 	tax_code_ref = row.get('JournalEntryLineDetail').get('TaxCodeRef')
# 	tax_head = ''
# 	if tax_code_ref and not tax_code_ref.get('value') == 'NON':
# 		if row.get('JournalEntryLineDetail').get('TaxApplicableOn') == "Sales":
# 			condition = "(select * from `tabQuickBooks SalesTaxRateList` where parent = {0}) as qbs " .format(tax_code_ref.get('value'))
# 		elif row.get('JournalEntryLineDetail').get('TaxApplicableOn') == "Purchase":
# 			condition = "(select * from `tabQuickBooks PurchaseTaxRateList` where parent = {0}) as qbs" .format(tax_code_ref.get('value')) 
# 		query = """select 
# 					qbr.name, qbr.display_name as tax_head, qbr.rate_value as tax_percent
# 				from
# 					`tabQuickBooks TaxRate` as qbr, {0}
# 				where
# 					qbr.tax_rate_id = qbs.tax_rate_id """.format(condition)
# 		individual_item_tax =  frappe.db.sql(query, as_dict=1)	
# 		tax_head = individual_item_tax[0]['tax_head']
# 	tax_account = get_tax_head_mapped_to_particular_account(tax_head, quickbooks_settings)
# 	return tax_account

# def get_tax_head_mapped_to_particular_account(tax_head, quickbooks_settings):

# 	""" fetch respective tax head from Tax Head Mappe table """
# 	account_head_erpnext =frappe.db.get_value("Tax Head Mapper", {"tax_head_quickbooks": tax_head, \
# 			"parent": "Quickbooks Settings"}, "account_head_erpnext")
# 	if not account_head_erpnext:
# 		account_head_erpnext = quickbooks_settings.undefined_tax_account
# 	account_head_erpnext = frappe.db.get_value("Account", {"name": account_head_erpnext}, ["name", "account_currency"], as_dict=1)
# 	return account_head_erpnext

