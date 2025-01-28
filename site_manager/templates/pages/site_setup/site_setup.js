frappe.ready(function() {
    let selectedPlan = null;
    let subdomainTimer = null;
    
    // Load available plans
    const loadPlans = () => {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Site Plan',
                fields: ['name', 'plan_name', 'price_monthly', 'max_users']
            },
            callback: function(response) {
                const plansContainer = document.getElementById('plans-container');
                plansContainer.innerHTML = response.message.map(plan => `
                    <div class="col-md-4 mb-4">
                        <div class="plan-card" data-plan="${plan.name}">
                            <h4>${plan.plan_name}</h4>
                            <div class="price">$${plan.price_monthly}/month</div>
                            <div class="details mt-3">
                                <div>Up to ${plan.max_users} users</div>
                            </div>
                        </div>
                    </div>
                `).join('');
                
                // Add click handlers to plan cards
                document.querySelectorAll('.plan-card').forEach(card => {
                    card.addEventListener('click', function() {
                        document.querySelectorAll('.plan-card').forEach(c => 
                            c.classList.remove('selected'));
                        this.classList.add('selected');
                        selectedPlan = this.dataset.plan;
                    });
                });
            }
        });
    };
    
    // Check subdomain availability
    const checkSubdomain = (subdomain) => {
        if (!subdomain) {
            document.getElementById('subdomain-status').innerHTML = '';
            return;
        }
        
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Site Subscription',
                filters: {
                    subdomain: subdomain
                }
            },
            callback: function(response) {
                const statusEl = document.getElementById('subdomain-status');
                if (response.message && response.message.length > 0) {
                    statusEl.innerHTML = 'This subdomain is already taken';
                    statusEl.classList.remove('text-success');
                    statusEl.classList.add('text-danger');
                } else {
                    statusEl.innerHTML = 'Subdomain is available!';
                    statusEl.classList.remove('text-danger');
                    statusEl.classList.add('text-success');
                }
            }
        });
    };
    
    // Set up subdomain input handler
    document.getElementById('subdomain').addEventListener('input', function(e) {
        if (subdomainTimer) {
            clearTimeout(subdomainTimer);
        }
        
        const subdomain = e.target.value.toLowerCase();
        // Update input to allowed characters only
        e.target.value = subdomain.replace(/[^a-z0-9]/g, '');
        
        subdomainTimer = setTimeout(() => {
            checkSubdomain(subdomain);
        }, 500);
    });
    
    // Set up create site button handler
    document.getElementById('create-site-btn').addEventListener('click', function() {
        const subdomain = document.getElementById('subdomain').value;
        
        if (!subdomain) {
            frappe.throw(__('Please enter a subdomain'));
            return;
        }
        
        if (!selectedPlan) {
            frappe.throw(__('Please select a plan'));
            return;
        }
        
        frappe.call({
            method: 'frappe.client.insert',
            args: {
                doc: {
                    doctype: 'Site Subscription',
                    subdomain: subdomain,
                    site_plan: selectedPlan
                }
            },
            callback: function(response) {
                if (!response.exc) {
                    frappe.show_alert({
                        message: __('Site creation started! You will receive an email when it\'s ready.'),
                        indicator: 'green'
                    });
                    setTimeout(() => {
                        window.location.href = '/me';
                    }, 2000);
                }
            }
        });
    });
    
    // Load plans on page load
    loadPlans();
});