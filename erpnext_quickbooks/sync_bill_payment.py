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
def sync_bill_payments(quickbooks_obj): 
	"""Fetch payment data from QuickBooks"""
	quickbooks_bill_payment_list = []  
	business_objects = "BillPayment"
	get_qb_payments =  pagination(quickbooks_obj, business_objects)
	if get_qb_payments:
		sync_qb_bill_payments(get_qb_payments, quickbooks_bill_payment_list)

def sync_qb_bill_payments(get_qb_payments, quickbooks_bill_payment_list):
	company_name = frappe.defaults.get_defaults().get("company")
	default_currency = frappe.db.get_value("Company" ,{"name":company_name},"default_currency")
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	for qb_payment in get_qb_payments:
		try:
			create_jv_from_qb_billpayment(qb_payment,quickbooks_settings,quickbooks_bill_payment_list)
		except Exception, e:
			make_quickbooks_log(title=e.message, status="Error", method="sync_bill_payments", message=frappe.get_traceback(),
						request_data=qb_payment, exception=True)
			
def create_jv_from_qb_billpayment(qb_payment,quickbooks_settings,quickbooks_bill_payment_list):
	qb_payment_id = ''
	if qb_payment.get('Id'):
		qb_payment_id = "JE" + qb_payment.get('Id')
	try:	
		if not 	frappe.db.get_value("Journal Entry", {"quickbooks_payment_id": qb_payment_id}, "name"): 
			journal = frappe.new_doc("Journal Entry")
			journal.qb_payment_id = qb_payment_id
			journal.voucher_type = _("Journal Entry")
			journal.naming_series = "JE-Quickbooks-"
			journal.posting_date = qb_payment.get('TxnDate')
			journal.multi_currency = 1
			journal.total_debit = qb_payment.get('TotalAmt')
			journal.total_credit =  qb_payment.get('TotalAmt')
			get_journal_entry_accounts(journal, qb_payment, quickbooks_settings)
			# journal.flags.ignore_validate = True
			# journal.flags.ignore_mandatory = True
			journal.save()
			journal.submit()
			frappe.db.commit()
			quickbooks_bill_payment_list.append(journal.qb_payment_id)
	except Exception, e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_quickbooks_log(title=e.message, status="Error", method="create_jv_from_qb_payment", message=frappe.get_traceback(),
				request_data=qb_payment, exception=True)
	
def get_journal_entry_accounts(journal, qb_payment, quickbooks_settings):
	debit_entry = credit_entry = 1
	company_name = frappe.defaults.get_defaults().get("company")
	for bill in qb_payment.get('Line'):
		pi_name = frappe.db.get_value("Purchase Invoice", {"quickbooks_purchase_invoice_id": bill.get('LinkedTxn')[0].get('TxnId')}, "name")
		if pi_name:
			cash_account = frappe.db.get_value("Company", {"name": company_name}, "default_bank_account")
			credit_to = frappe.db.get_value("Purchase Invoice", {"name": pi_name}, "credit_to")
	 		# expense_account = frappe.db.get_value("Purchase Invoice Item", {"parent": pi_name}, "expense_account")
			if debit_entry:
				account = journal.append("accounts", {})
				account.account = credit_to
				account.reference_type = "Purchase Invoice"
				account.reference_name = pi_name
				account.party = qb_payment.get('VendorRef').get('name')
				account.party_type ="Supplier"
				account.debit_in_account_currency = bill.get('Amount')
			if credit_entry:
				account = journal.append("accounts", {})
				account.credit_in_account_currency = bill.get('Amount')
				account.account = cash_account

	# print " Inprocess for get_journal_entry_accounts "
	# debit_entry = credit_entry = 1
	# company_name = frappe.defaults.get_defaults().get("company")
	# if debit_entry:
	# 	default_receivable_account = frappe.db.get_value("Company", {"name": company_name}, "default_receivable_account")
	# 	account = journal.append("accounts", {})
	# 	account.account = "Sales - AALDC"
	# 	account.debit_in_account_currency = qb_payment.get('TotalAmt')
	# 	account.idx = 1		
	# if credit_entry:
	# 	default_payable_account = frappe.db.get_value("Company", {"name": company_name}, "default_payable_account")
	# 	account = journal.append("accounts", {})
	# 	account.credit_in_account_currency = qb_payment.get('TotalAmt')
	# 	account.account = default_payable_account
	# 	account.reference_type = "Sales Invoice"
	# 	si_name = frappe.db.get_value("Sales Invoice", {"quickbooks_invoice_no": qb_payment.get('Line')[0].get('LineEx').get('any')[2].get('value').get('Value')}, "name")
	# 	account.reference_name = si_name
	# 	account.party = qb_payment.get('CustomerRef').get('name')
	# 	account.party_type ="Customer"
	# 	account.idx = 2