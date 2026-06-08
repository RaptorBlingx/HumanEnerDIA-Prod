// Sidebar Component for HUMANERGY Portal
// This file provides a unified navigation sidebar for all pages

// Insert sidebar HTML into the page
function initializeSidebar() {
    const sidebarHTML = `
    <!-- Sidebar Menu -->
    <div id="sidebar" class="sidebar">
        <div class="sidebar-header">
            <h3>Menu</h3>
            <button onclick="toggleSidebar()" class="close-btn">&times;</button>
        </div>
        <div class="sidebar-content">
            <!-- Dashboard Links (Only for Authenticated Users) -->
            <div id="dashboard-section" class="sidebar-section" style="display: none;">
                <div class="sidebar-section-title">Dashboard</div>
                <a href="/index.html" class="sidebar-link">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="7" height="7"></rect>
                        <rect x="14" y="3" width="7" height="7"></rect>
                        <rect x="14" y="14" width="7" height="7"></rect>
                        <rect x="3" y="14" width="7" height="7"></rect>
                    </svg>
                    Dashboard
                </a>
                
                <!-- Analytics Expandable Menu -->
                <button class="sidebar-link-expandable" onclick="toggleSubmenu('analytics-submenu')">
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="20" x2="18" y2="10"></line>
                            <line x1="12" y1="20" x2="12" y2="4"></line>
                            <line x1="6" y1="20" x2="6" y2="14"></line>
                        </svg>
                        <span>Analytics</span>
                    </div>
                    <span class="expand-icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="9 18 15 12 9 6"></polyline>
                        </svg>
                    </span>
                </button>
                <div id="analytics-submenu" class="sidebar-submenu">
                    <a href="/api/analytics/ui/" class="sidebar-link">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path>
                            <path d="M22 12A10 10 0 0 0 12 2v10z"></path>
                        </svg>
                        Dashboard
                    </a>
                    <a href="/api/analytics/ui/baseline" class="sidebar-link">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                            <polyline points="2 17 12 22 22 17"></polyline>
                            <polyline points="2 12 12 17 22 12"></polyline>
                        </svg>
                        Baseline
                    </a>
                    <a href="/api/analytics/ui/anomaly" class="sidebar-link">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                            <line x1="12" y1="9" x2="12" y2="13"></line>
                            <line x1="12" y1="17" x2="12.01" y2="17"></line>
                        </svg>
                        Anomalies
                    </a>
                    <a href="/api/analytics/ui/kpi" class="sidebar-link">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <circle cx="12" cy="12" r="6"></circle>
                            <circle cx="12" cy="12" r="2"></circle>
                        </svg>
                        KPIs
                    </a>
                    <a href="/api/analytics/ui/forecast" class="sidebar-link">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline>
                            <polyline points="17 6 23 6 23 12"></polyline>
                        </svg>
                        Forecasting
                    </a>
                    
                    <!-- Visualizations Nested Submenu -->
                    <button class="sidebar-link-expandable" onclick="toggleSubmenu('viz-submenu')" style="padding-left: 3rem;">
                        <div style="display: flex; align-items: center; gap: 1rem;">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <line x1="3" y1="9" x2="21" y2="9"></line>
                                <line x1="9" y1="21" x2="9" y2="9"></line>
                            </svg>
                            <span>Visualizations</span>
                        </div>
                        <span class="expand-icon">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                        </span>
                    </button>
                    <div id="viz-submenu" class="sidebar-submenu">
                        <a href="/api/analytics/ui/sankey" class="sidebar-link">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="16 3 21 3 21 8"></polyline>
                                <line x1="4" y1="20" x2="21" y2="3"></line>
                                <polyline points="21 16 21 21 16 21"></polyline>
                                <line x1="15" y1="15" x2="21" y2="21"></line>
                                <line x1="4" y1="4" x2="9" y2="9"></line>
                            </svg>
                            Sankey Diagram
                        </a>
                        <a href="/api/analytics/ui/heatmap" class="sidebar-link">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"></path>
                            </svg>
                            Anomaly Heatmap
                        </a>
                        <a href="/api/analytics/ui/comparison" class="sidebar-link">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-7m0-18H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h7m0-18v18"></path>
                            </svg>
                            Machine Comparison
                        </a>
                        <a href="/api/analytics/ui/model-performance" class="sidebar-link">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="4" y1="21" x2="4" y2="14"></line>
                                <line x1="4" y1="10" x2="4" y2="3"></line>
                                <line x1="12" y1="21" x2="12" y2="12"></line>
                                <line x1="12" y1="8" x2="12" y2="3"></line>
                                <line x1="20" y1="21" x2="20" y2="16"></line>
                                <line x1="20" y1="12" x2="20" y2="3"></line>
                                <line x1="1" y1="14" x2="7" y2="14"></line>
                                <line x1="9" y1="8" x2="15" y2="8"></line>
                                <line x1="17" y1="16" x2="23" y2="16"></line>
                            </svg>
                            Model Performance
                        </a>
                    </div>
                </div>
                
                <a href="/reports.html" class="sidebar-link">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                        <line x1="16" y1="13" x2="8" y2="13"></line>
                        <line x1="16" y1="17" x2="8" y2="17"></line>
                        <polyline points="10 9 9 9 8 9"></polyline>
                    </svg>
                    Reports
                </a>
                <a href="/grafana/" class="sidebar-link" target="_blank">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="20" x2="12" y2="10"></line>
                        <line x1="18" y1="20" x2="18" y2="4"></line>
                        <line x1="6" y1="20" x2="6" y2="16"></line>
                    </svg>
                    Grafana
                </a>
                <a href="/nodered/" class="sidebar-link" target="_blank">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg>
                    Node-RED
                </a>
                <a href="/api/simulator/docs" class="sidebar-link" target="_blank">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polygon points="10 8 16 12 10 16 10 8"></polygon>
                    </svg>
                    Simulator
                </a>
                <div class="sidebar-divider"></div>
            </div>

            <!-- Public Pages (Always Visible) -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Information</div>
                <a href="/about.html" class="sidebar-link">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <path d="M12 16v-4"></path>
                        <path d="M12 8h.01"></path>
                    </svg>
                    About
                </a>
                <a href="/iso50001.html" class="sidebar-link">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    ISO 50001
                </a>
                <a href="/contact.html" class="sidebar-link">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    Contact
                </a>
            </div>
            
            <div class="sidebar-divider"></div>
            
            <!-- Authentication Link (Only for Non-Authenticated Users) -->
            <a id="sidebar-auth-btn" href="/auth.html" class="sidebar-link" style="display: none;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                    <polyline points="10 17 15 12 10 7"></polyline>
                    <line x1="15" y1="12" x2="3" y2="12"></line>
                </svg>
                Sign In
            </a>
            
            <!-- Admin Dashboard (Only for Admins) -->
            <a id="sidebar-admin-btn" href="/admin/dashboard.html" class="sidebar-link admin-link" style="display: none;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="8.5" cy="7" r="4"></circle>
                    <polyline points="17 11 19 13 23 9"></polyline>
                </svg>
                Admin Dashboard
            </a>
            
            <!-- Logout (Only for Authenticated Users) -->
            <a id="sidebar-logout-btn" href="#" onclick="logout(); return false;" class="sidebar-link logout-link" style="display: none;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                Logout
            </a>
        </div>
    </div>

    <!-- Sidebar Overlay -->
    <div id="sidebar-overlay" class="sidebar-overlay" onclick="toggleSidebar()"></div>
    `;
    
    // Insert sidebar at the beginning of body
    document.body.insertAdjacentHTML('afterbegin', sidebarHTML);
    
    // Apply conditional display based on authentication status
    updateSidebarVisibility();

    // Highlight current page
    setActiveSidebarLink();
    
    // Auto-expand analytics menu if on analytics page
    if (window.location.pathname.includes('/api/analytics/ui')) {
        const analyticsSubmenu = document.getElementById('analytics-submenu');
        const analyticsBtn = analyticsSubmenu.previousElementSibling;
        if (analyticsSubmenu && analyticsBtn) {
            analyticsSubmenu.classList.add('expanded');
            analyticsBtn.classList.add('expanded');
        }
        
        // Auto-expand viz submenu if on viz page
        if (window.location.pathname.includes('/sankey') || 
            window.location.pathname.includes('/heatmap') || 
            window.location.pathname.includes('/comparison') || 
            window.location.pathname.includes('/model-performance')) {
            const vizSubmenu = document.getElementById('viz-submenu');
            const vizBtn = vizSubmenu.previousElementSibling;
            if (vizSubmenu && vizBtn) {
                vizSubmenu.classList.add('expanded');
                vizBtn.classList.add('expanded');
            }
        }
    }
}

// Toggle submenu expansion
function toggleSubmenu(submenuId) {
    const submenu = document.getElementById(submenuId);
    const button = submenu.previousElementSibling;
    
    submenu.classList.toggle('expanded');
    button.classList.toggle('expanded');
}

function setActiveSidebarLink() {
    const rawPath = window.location.pathname || '/';
    const currentPath = rawPath.replace(/\/+$/, '') || '/';

    const links = document.querySelectorAll('#sidebar .sidebar-link');
    links.forEach(link => {
        link.classList.remove('active');

        const href = link.getAttribute('href');
        if (!href || href === '#' || href.startsWith('http') || href.startsWith('#')) return;

        const normalizedHref = href.replace(/\/+$/, '') || '/';
        const isIndexMatch = normalizedHref === '/' && (currentPath === '/' || currentPath === '/index.html');
        const isExactMatch = normalizedHref === currentPath;

        if (isIndexMatch || isExactMatch) {
            link.classList.add('active');
        }
    });
}

// Update sidebar visibility based on authentication status
function updateSidebarVisibility() {
    const token = localStorage.getItem('auth_token');
    const userData = JSON.parse(localStorage.getItem('user_data') || '{}');
    const isAuthenticated = token && userData.email;
    
    // Dashboard section - only for authenticated users
    const dashboardSection = document.getElementById('dashboard-section');
    if (dashboardSection) {
        dashboardSection.style.display = isAuthenticated ? 'block' : 'none';
    }
    
    // Auth button - only for non-authenticated users
    const authBtn = document.getElementById('sidebar-auth-btn');
    if (authBtn) {
        authBtn.style.display = isAuthenticated ? 'none' : 'flex';
    }
    
    // Admin button - only for authenticated admin users
    const adminBtn = document.getElementById('sidebar-admin-btn');
    if (adminBtn && userData.role === 'admin') {
        adminBtn.style.display = 'flex';
    }
    
    // Logout button - only for authenticated users
    const logoutBtn = document.getElementById('sidebar-logout-btn');
    if (logoutBtn) {
        logoutBtn.style.display = isAuthenticated ? 'flex' : 'none';
    }
}

// Toggle sidebar function
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    
    if (sidebar && overlay) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('show');
    }
}

// Logout function
function logout() {
    // Call logout API
    const token = localStorage.getItem('auth_token');
    if (token) {
        fetch('/api/auth/logout', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        }).catch(err => console.error('Logout error:', err));
    }
    
    // Clear local storage
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_data');
    
    // Redirect to about page (new landing page)
    window.location.href = '/about.html';
}

// Initialize sidebar when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSidebar);
} else {
    initializeSidebar();
}
