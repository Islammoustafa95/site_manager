from frappe import _

def get_site_setup_page(context):
    context.no_cache = 1
    if frappe.session.user == 'Guest':
        frappe.throw(_("Please login first"), frappe.PermissionError)
    return "site_manager/templates/pages/site_setup.html"