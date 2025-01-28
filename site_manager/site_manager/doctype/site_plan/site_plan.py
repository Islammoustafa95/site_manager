import frappe
from frappe.model.document import Document

class SitePlan(Document):
    def validate(self):
        self.validate_apps()
    
    def validate_apps(self):
        """Ensure all selected apps are supported"""
        supported_apps = ["erpnext", "hrms", "payments"]
        for app in self.apps:
            if app.app_name not in supported_apps:
                frappe.throw(f"App {app.app_name} is not supported. Available apps: {', '.join(supported_apps)}")
    
    def on_update(self):
        """Clear cache when plan is updated"""
        frappe.cache().delete_key('site_plans')
    
    @staticmethod
    def get_available_apps():
        """Get list of available apps for plan selection"""
        return frappe.get_installed_apps()
    
    def after_insert(self):
        """Clear cache when new plan is created"""
        frappe.cache().delete_key('site_plans')
    
    def on_trash(self):
        """
        Validate if plan can be deleted
        Prevent deletion if there are active subscriptions
        """
        active_subscriptions = frappe.get_all(
            "Site Subscription",
            filters={
                "site_plan": self.name,
                "status": ["in", ["Active", "Pending", "In Progress"]]
            }
        )
        
        if active_subscriptions:
            frappe.throw(
                "Cannot delete this plan as there are active subscriptions. "
                "Please cancel all subscriptions first."
            )