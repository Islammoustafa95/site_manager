import frappe
from frappe.model.document import Document
import subprocess
import os
import time
import requests
from frappe.utils import now_datetime, cint
import json
import shutil

# Cloudflare configuration
CLOUDFLARE_CONFIG = {
    'zone_id': '9029e72b2677719d64522a5275d5e062',
    'account_id': '245f77417234440a38584671e8efebd6',
    'api_token': 'AJNh7kK1r7LQn1Rv5HDUkKH8c7t46I1lzeO4AB_2'
}

MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def get_db_root_password():
    """Get the MariaDB root password from common site config"""
    config_path = os.path.join(os.path.dirname(frappe.get_site_path()), 'common_site_config.json')
    try:
        with open(config_path) as f:
            config = json.load(f)
            return config.get('db_root_password', '')
    except Exception as e:
        frappe.log_error(f"Error reading root password: {str(e)}")
        return ''

def execute_command(cmd, log_prefix="", retries=MAX_RETRIES):
    """Execute a command with retry mechanism and detailed logging"""
    frappe.logger().info(f"Executing command: {cmd}")
    
    for attempt in range(retries):
        if attempt > 0:
            frappe.logger().info(f"Retry attempt {attempt + 1}/{retries} for command: {cmd}")
            
        process = subprocess.Popen(
            cmd.split(), 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Real-time output logging
        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()
            
            if stdout_line == '' and stderr_line == '' and process.poll() is not None:
                break
                
            if stdout_line:
                frappe.logger().info(f"Command output: {stdout_line.strip()}")
            if stderr_line:
                frappe.logger().error(f"Command error: {stderr_line.strip()}")
                
        output, error = process.communicate()
        success = process.returncode == 0
        
        if success:
            frappe.logger().info(f"Command completed successfully: {cmd}")
            log = f"{log_prefix}\nCommand: {cmd}\nOutput: {output}\nError: {error}\n"
            return success, log
        
        if attempt < retries - 1:
            time.sleep(RETRY_DELAY)
            continue
    
    frappe.logger().error(f"Command failed after {retries} attempts: {cmd}")
    log = f"{log_prefix}\nCommand: {cmd}\nOutput: {output}\nError: {error}\n"
    return success, log

def update_subscription_status(doc, status, log_message, progress=None):
    """Update subscription document status, logs and progress"""
    doc.status = status
    if progress is not None:
        doc.progress = cint(progress)
    doc.creation_logs = (doc.creation_logs or "") + f"\n[{now_datetime()}] {log_message}"
    doc.save()
    frappe.db.commit()

def check_site_health(site_name):
    """Check if the site is responding and healthy"""
    try:
        # Try to access the site
        response = requests.get(f"https://{site_name}", timeout=30, verify=False)
        if response.status_code != 200:
            return False, f"Site health check failed with status code: {response.status_code}"
        
        # Check if Frappe is working by accessing the login page
        response = requests.get(f"https://{site_name}/login", timeout=30, verify=False)
        if response.status_code != 200:
            return False, f"Login page check failed with status code: {response.status_code}"
        
        return True, "Site health check passed"
    except Exception as e:
        return False, f"Site health check failed: {str(e)}"

def setup_cloudflare_dns(subdomain, retry_count=3):
    """Setup Cloudflare DNS A record for the subdomain"""
    headers = {
        'Authorization': f'Bearer {CLOUDFLARE_CONFIG["api_token"]}',
        'Content-Type': 'application/json'
    }
    
    # Get server IP address
    try:
        response = requests.get('https://api.ipify.org?format=json')
        server_ip = response.json()['ip']
    except Exception as e:
        return False, f"Failed to get server IP: {str(e)}"

    data = {
        'type': 'A',
        'name': subdomain,
        'content': server_ip,
        'ttl': 1,  # Auto TTL
        'proxied': True
    }

    url = f'https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_CONFIG["zone_id"]}/dns_records'

    for attempt in range(retry_count):
        try:
            response = requests.post(url, headers=headers, json=data)
            response_data = response.json()

            if response.status_code == 200 and response_data.get('success'):
                return True, f"DNS record created successfully for {subdomain}"
            
            error_message = response_data.get('errors', [{'message': 'Unknown error'}])[0].get('message')
            if attempt < retry_count - 1:
                time.sleep(5)  # Wait before retry
                continue
                
            return False, f"Failed to create DNS record: {error_message}"

        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(5)
                continue
            return False, f"Error creating DNS record: {str(e)}"

    return False, "Failed to create DNS record after all retries"

def cleanup_failed_site(site_name, bench_path="/home/frappe/frappe-bench"):
    """Clean up site files and database if site creation fails"""
    try:
        # Remove site directory
        site_path = os.path.join(bench_path, "sites", site_name)
        if os.path.exists(site_path):
            shutil.rmtree(site_path)
        
        # Drop databases
        root_password = get_db_root_password()
        if root_password:
            site_db = site_name.replace('.', '_')
            cmds = [
                f"mysql -uroot -p{root_password} -e 'DROP DATABASE IF EXISTS {site_db}'",
                f"mysql -uroot -p{root_password} -e 'DROP DATABASE IF EXISTS {site_db}_backup'"
            ]
            for cmd in cmds:
                subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Remove Cloudflare DNS record
        headers = {
            'Authorization': f'Bearer {CLOUDFLARE_CONFIG["api_token"]}',
            'Content-Type': 'application/json'
        }
        
        # First, get the DNS record ID
        url = f'https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_CONFIG["zone_id"]}/dns_records'
        response = requests.get(url, headers=headers, params={'name': site_name})
        
        if response.status_code == 200:
            records = response.json().get('result', [])
            for record in records:
                # Delete the record
                delete_url = f'{url}/{record["id"]}'
                requests.delete(delete_url, headers=headers)
        
        return True, "Cleanup completed successfully"
    except Exception as e:
        return False, f"Cleanup failed: {str(e)}"

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
    """Background job to create a new site with enhanced monitoring and recovery"""
    try:
        doc = frappe.get_doc("Site Subscription", subscription)
        doc.creation_logs = ""
        doc.progress = 0
        update_subscription_status(doc, "In Progress", "Starting site creation process...", 0)
        
        site_name = f"{doc.subdomain}.zaynerp.com"
        plan = frappe.get_doc("Site Plan", doc.site_plan)
        
        # Get root password from config
        root_password = get_db_root_password()
        if not root_password:
            raise Exception("Database root password not configured")

        # Step 1: Create new site (20%)
        update_subscription_status(doc, "In Progress", "Creating new site...", 10)
        success, log = execute_command(
            f"bench new-site {site_name} --mariadb-root-password {root_password} --admin-password admin"
        )
        if not success:
            raise Exception(f"Site creation failed: {log}")
        update_subscription_status(doc, "In Progress", log, 20)
        
        time.sleep(2)

        # Step 2: Domain setup (30%)
        update_subscription_status(doc, "In Progress", "Setting up domain...", 25)
        success, log = execute_command(
            f"bench setup add-domain {site_name} --site {site_name}"
        )
        if not success:
            raise Exception(f"Domain setup failed: {log}")
        update_subscription_status(doc, "In Progress", log, 30)

        time.sleep(2)

        # Step 3: Cloudflare DNS setup (40%)
        update_subscription_status(doc, "In Progress", "Setting up Cloudflare DNS...", 35)
        dns_success, dns_log = setup_cloudflare_dns(site_name)
        if not dns_success:
            raise Exception(f"Cloudflare DNS setup failed: {dns_log}")
        update_subscription_status(doc, "In Progress", dns_log, 40)

        time.sleep(2)

        # Step 4: Install apps one by one (40-90%)
        total_apps = len(plan.apps)
        progress_per_app = 50 / total_apps if total_apps > 0 else 0
        
        for index, app in enumerate(plan.apps):
            current_progress = 40 + (index * progress_per_app)
            app_name = app.app_name
            
            update_subscription_status(
                doc, 
                "In Progress", 
                f"Starting installation of app {index + 1}/{total_apps}: {app_name}...",
                current_progress
            )

            # Enable the site first
            update_subscription_status(doc, "In Progress", f"Enabling site for {app_name} installation...", current_progress + 2)
            success, enable_log = execute_command(f"bench --site {site_name} enable-scheduler")
            if not success:
                frappe.logger().warning(f"Enable scheduler warning: {enable_log}")

            time.sleep(2)
            
            # Install the app with detailed logging
            update_subscription_status(doc, "In Progress", f"Installing {app_name}...", current_progress + 5)
            install_cmd = f"bench --site {site_name} install-app {app_name}"
            
            process = subprocess.Popen(
                install_cmd.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            install_output = []
            while True:
                output_line = process.stdout.readline()
                error_line = process.stderr.readline()
                
                if output_line == '' and error_line == '' and process.poll() is not None:
                    break
                    
                if output_line:
                    install_output.append(output_line.strip())
                    update_subscription_status(
                        doc, 
                        "In Progress", 
                        f"Installing {app_name}: {output_line.strip()}",
                        current_progress + 10
                    )
                if error_line:
                    install_output.append(f"Error: {error_line.strip()}")
                    update_subscription_status(
                        doc, 
                        "In Progress", 
                        f"Installing {app_name} (Error): {error_line.strip()}",
                        current_progress + 10
                    )
            
            install_success = process.returncode == 0
            if not install_success:
                raise Exception(f"App installation failed for {app_name}:\n{''.join(install_output)}")
            
            update_subscription_status(
                doc, 
                "In Progress", 
                f"Finished installing {app_name}",
                current_progress + (progress_per_app * 0.6)
            )
            
            time.sleep(5)  # Longer wait after installation
            
            # Run migration with detailed logging
            update_subscription_status(
                doc, 
                "In Progress", 
                f"Starting migration for {app_name}...",
                current_progress + (progress_per_app * 0.7)
            )
            
            migrate_cmd = f"bench --site {site_name} migrate"
            process = subprocess.Popen(
                migrate_cmd.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            migrate_output = []
            while True:
                output_line = process.stdout.readline()
                error_line = process.stderr.readline()
                
                if output_line == '' and error_line == '' and process.poll() is not None:
                    break
                    
                if output_line:
                    migrate_output.append(output_line.strip())
                    update_subscription_status(
                        doc, 
                        "In Progress", 
                        f"Migrating {app_name}: {output_line.strip()}",
                        current_progress + (progress_per_app * 0.8)
                    )
                if error_line:
                    migrate_output.append(f"Error: {error_line.strip()}")
                    update_subscription_status(
                        doc, 
                        "In Progress", 
                        f"Migrating {app_name} (Error): {error_line.strip()}",
                        current_progress + (progress_per_app * 0.8)
                    )
            
            migrate_success = process.returncode == 0
            if not migrate_success:
                raise Exception(f"Migration failed for {app_name}:\n{''.join(migrate_output)}")
            
            update_subscription_status(
                doc, 
                "In Progress", 
                f"Finished migration for {app_name}",
                current_progress + progress_per_app
            )
            
            time.sleep(5)  # Longer wait after migration

        # Step 5: Nginx Configuration (90-95%)
        update_subscription_status(doc, "In Progress", "Configuring nginx...", 90)
        
        # Setup nginx with empty log format and auto-yes
        nginx_cmd = "bench setup nginx --yes --log-format ''"
        process = subprocess.Popen(nginx_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        log = f"Nginx Setup\nOutput: {output.decode()}\nError: {error.decode()}\n"
        update_subscription_status(doc, "In Progress", log, 92)
        
        time.sleep(2)

        # Restart and reload nginx
        update_subscription_status(doc, "In Progress", "Restarting nginx...", 93)
        
        # Stop nginx first
        execute_command("sudo service nginx stop")
        time.sleep(2)
        
        # Start nginx
        success, log = execute_command("sudo service nginx start")
        if not success:
            raise Exception(f"Nginx start failed: {log}")
        update_subscription_status(doc, "In Progress", log, 94)
        
        time.sleep(2)
        
        # Reload nginx
        success, log = execute_command("sudo service nginx reload")
        if not success:
            raise Exception(f"Nginx reload failed: {log}")
        update_subscription_status(doc, "In Progress", log, 95)

        # Step 6: Health Check (95-100%)
        update_subscription_status(doc, "In Progress", "Performing health checks...", 98)
        health_success, health_message = check_site_health(site_name)
        if not health_success:
            raise Exception(f"Site health check failed: {health_message}")
        update_subscription_status(doc, "In Progress", f"Health check result: {health_message}", 99)

        # Final status update
        update_subscription_status(doc, "Active", "Site creation completed successfully!", 100)
        
        # Send success email
        frappe.sendmail(
            recipients=[doc.user],
            subject=f"Your site {site_name} is ready!",
            message=f"""
            Your new site has been created and is ready to use.
            Site URL: https://{site_name}
            Admin Username: Administrator
            Admin Password: admin
            
            Please make sure to change your admin password after first login.
            """
        )
        
    except Exception as e:
        error_msg = str(e)
        frappe.logger().error(f"Site creation failed for {subscription}: {error_msg}")
        
        # Attempt cleanup
        update_subscription_status(doc, "Failed", "Starting cleanup process...")
        cleanup_success, cleanup_msg = cleanup_failed_site(site_name)
        cleanup_log = "Cleanup successful" if cleanup_success else f"Cleanup failed: {cleanup_msg}"
        update_subscription_status(doc, "Failed", f"Error: {error_msg}\n{cleanup_log}")
        
        # Send failure notification
        frappe.sendmail(
            recipients=[doc.user],
            subject=f"Site creation failed for {site_name}",
            message=f"""
            We encountered an error while setting up your site.
            Error: {error_msg}
            
            Our team has been notified and will look into this issue.
            """
        )

def after_insert(doc, method):
    """Queues the site creation background job"""
    # Immediately update status to In Progress
    doc.status = "In Progress"