import frappe
from frappe.model.document import Document
import subprocess
import os
from frappe.utils import now_datetime

class SiteSubscription(Document):
    def validate(self):
        if not self.creation_date:
            self.creation_date = now_datetime()
        
        if not self.user:
            self.user = frappe.session.user
            
        # Validate subdomain
        if not self.subdomain.isalnum():
            frappe.throw("Subdomain can only contain letters and numbers")
            
        if len(self.subdomain) < 3:
            frappe.throw("Subdomain must be at least 3 characters long")

def create_new_site(subscription):
    """Background job to create a new site"""
    try:
        doc = frappe.get_doc("Site Subscription", subscription)
        doc.status = "In Progress"
        doc.save()
        
        site_name = f"{doc.subdomain}.zaynerp.com"
        
        # Get the plan details
        plan = frappe.get_doc("Site Plan", doc.site_plan)
        
        # Step 1: Create new site
        cmd = f"bench new-site {site_name} --admin-password admin"
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        
        log_output = f"Site creation output:\n{output.decode()}\n{error.decode()}\n"
        
        # Step 2: Install apps
        for app in plan.apps:
            cmd = f"bench --site {site_name} install-app {app.app_name}"
            process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, error = process.communicate()
            log_output += f"App {app.app_name} installation:\n{output.decode()}\n{error.decode()}\n"
        
        # Step 3: Run migrations
        cmd = f"bench --site {site_name} migrate"
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        log_output += f"Migration output:\n{output.decode()}\n{error.decode()}\n"
        
        # Step 4: Add domain
        cmd = f"bench setup add-domain {site_name}"
        process = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        log_output += f"Domain setup output:\n{output.decode()}\n{error.decode()}\n"
        
        # Update document status
        doc.status = "Active"
        doc.creation_logs = log_output
        doc.save()
        
        # Send email notification
        frappe.sendmail(
            recipients=[doc.user],
            subject=f"Your site {site_name} is ready!",
            message=f"Your new site has been created and is ready to use. You can access it at https://{site_name}"
        )
        
    except Exception as e:
        frappe.log_error(f"Site creation failed for {subscription}: {str(e)}")
        doc = frappe.get_doc("Site Subscription", subscription)
        doc.status = "Failed"
        doc.creation_logs += f"\nError: {str(e)}"
        doc.save()

def after_insert(doc, method):
    """Queues the site creation background job"""
    frappe.enqueue(
        'site_manager.site_manager.doctype.site_subscription.site_subscription.create_new_site',
        queue='long',
        timeout=1500,
        subscription=doc.name
    )