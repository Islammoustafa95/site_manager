import frappe

def get_context(context):
    if frappe.session.user == 'Guest':
        frappe.throw('Please login to access this page', frappe.PermissionError)
    
    context.no_cache = 1
    context.show_sidebar = True
    
    # Get available plans
    context.plans = frappe.get_all('Site Plan',
        fields=['name', 'plan_name', 'price_monthly', 'max_users'],
        order_by='price_monthly asc'
    )
    
    # Get user's existing sites
    context.existing_sites = frappe.get_all('Site Subscription',
        filters={'user': frappe.session.user},
        fields=['name', 'subdomain', 'status', 'creation_date', 'site_plan']
    )
    
    return context