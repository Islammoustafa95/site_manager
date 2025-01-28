from . import __version__ as app_version

app_name = "site_manager"
app_title = "Site Manager"
app_publisher = "Your Company"
app_description = "Frappe/ERPNext Site Manager"
app_email = "your@email.com"
app_license = "MIT"

has_website_permission = {
    "Site Subscription": "site_manager.site_manager.doctype.site_subscription.site_subscription.has_website_permission"
}

doc_events = {
    "Site Subscription": {
        "after_insert": "site_manager.site_manager.doctype.site_subscription.site_subscription.after_insert"
    }
}

website_route_rules = [
    {"from_route": "/site-setup", "to_route": "site_setup"}
]

web_include_css = "/assets/site_manager/css/site_manager.css"
web_include_js = "/assets/site_manager/js/site_manager.js"