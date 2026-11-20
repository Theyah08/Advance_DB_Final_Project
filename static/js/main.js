/**
 * Prosfora Gift Shop POS System - Main Frontend Scripts
 * Handles layout interactions, sidebar toggling, alerts, and modal operations.
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Mobile Sidebar Toggle & Backdrop
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    
    function toggleSidebar(forceClose = false) {
        if (!sidebar) return;
        if (forceClose) {
            sidebar.classList.remove('mobile-open');
            if (sidebarBackdrop) sidebarBackdrop.classList.remove('active');
        } else {
            const isOpen = sidebar.classList.toggle('mobile-open');
            if (sidebarBackdrop) {
                if (isOpen) {
                    sidebarBackdrop.classList.add('active');
                } else {
                    sidebarBackdrop.classList.remove('active');
                }
            }
        }
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleSidebar();
        });
    }

    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', function () {
            toggleSidebar(true);
        });
    }

    // 2. Alert Dismissal
    const alertCloses = document.querySelectorAll('.alert-close');
    alertCloses.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const alert = this.closest('.alert');
            if (alert) {
                alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(() => alert.remove(), 300);
            }
        });
    });

    // Auto-fade notifications after 5 seconds
    setTimeout(function () {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function (alert) {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        });
    }, 5000);

    // 3. Generic Modal Triggers
    const modalCloseButtons = document.querySelectorAll('[data-dismiss="modal"]');
    modalCloseButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            const modal = this.closest('.modal-overlay');
            if (modal) {
                closeModal(modal);
            }
        });
    });

    // Close modal on clicking overlay backdrop
    const modalOverlays = document.querySelectorAll('.modal-overlay');
    modalOverlays.forEach(function (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === this) {
                closeModal(this);
            }
        });
    });

    // Close modal or mobile drawer on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            toggleSidebar(true);
            const activeModal = document.querySelector('.modal-overlay.active');
            if (activeModal) closeModal(activeModal);
        }
    });

    // Close mobile sidebar on window resize to desktop
    window.addEventListener('resize', function () {
        if (window.innerWidth > 992) {
            toggleSidebar(true);
        }
    });
});

/**
 * Open a specified modal element
 * @param {HTMLElement|string} modalElement 
 */
function openModal(modalElement) {
    const modal = typeof modalElement === 'string' ? document.getElementById(modalElement) : modalElement;
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close a specified modal element
 * @param {HTMLElement|string} modalElement 
 */
function closeModal(modalElement) {
    const modal = typeof modalElement === 'string' ? document.getElementById(modalElement) : modalElement;
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

/**
 * Helper to confirm critical actions
 * @param {string} message Confirmation warning text
 * @returns {boolean} True if confirmed
 */
function confirmAction(message) {
    return window.confirm(message || 'Are you sure you wish to proceed with this action?');
}
