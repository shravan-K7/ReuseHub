/**
 * ReuseHub - Interactive Modal Controller
 * Zero-dependency, accessible confirmation modals (Logout, Delete Item, etc.)
 */
(function () {
  'use strict';

  const ReuseHubModal = {
    activeModal: null,
    previousFocusedElement: null,

    open: function (target) {
      const modal = typeof target === 'string' ? document.querySelector(target) : target;
      if (!modal) return;

      // Close any open modal first
      if (this.activeModal && this.activeModal !== modal) {
        this.close(this.activeModal, false);
      }

      this.previousFocusedElement = document.activeElement;
      this.activeModal = modal;

      modal.style.display = 'flex';
      // Force reflow for CSS animation
      void modal.offsetWidth;
      modal.classList.add('show', 'is-active');
      document.body.classList.add('modal-open');

      // Accessibility: focus the first interactive element or cancel button
      const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (focusable.length > 0) {
        // Prefer cancel button or primary button
        const cancelBtn = modal.querySelector('[data-modal-close]') || focusable[0];
        if (cancelBtn) cancelBtn.focus();
      }

      const event = new CustomEvent('modal:opened', { detail: { modal: modal } });
      modal.dispatchEvent(event);
    },

    close: function (target, restoreFocus) {
      const modal = typeof target === 'string' ? document.querySelector(target) : (target || this.activeModal);
      if (!modal) return;

      modal.classList.remove('show', 'is-active');
      document.body.classList.remove('modal-open');

      setTimeout(function () {
        if (!modal.classList.contains('show')) {
          modal.style.display = 'none';
        }
      }, 220);

      if (this.activeModal === modal) {
        this.activeModal = null;
      }

      if (restoreFocus !== false && this.previousFocusedElement) {
        this.previousFocusedElement.focus();
        this.previousFocusedElement = null;
      }

      const event = new CustomEvent('modal:closed', { detail: { modal: modal } });
      modal.dispatchEvent(event);
    },

    closeAll: function () {
      document.querySelectorAll('.modal-backdrop.show, .modal-backdrop.is-active').forEach(function (m) {
        ReuseHubModal.close(m);
      });
    }
  };

  // Expose globally
  window.ReuseHubModal = ReuseHubModal;

  document.addEventListener('DOMContentLoaded', function () {
    // 1. Click triggers for data-modal-target / data-modal-open
    document.addEventListener('click', function (e) {
      // Open trigger
      const trigger = e.target.closest('[data-modal-target], [data-modal-open]');
      if (trigger) {
        e.preventDefault();
        const selector = trigger.getAttribute('data-modal-target') || trigger.getAttribute('data-modal-open');
        ReuseHubModal.open(selector);
        return;
      }

      // Close trigger
      const closeBtn = e.target.closest('[data-modal-close], .modal-close-btn');
      if (closeBtn) {
        e.preventDefault();
        const modal = closeBtn.closest('.modal-backdrop');
        if (modal) ReuseHubModal.close(modal);
        return;
      }

      // Click outside dialog (on backdrop itself)
      if (e.target.classList.contains('modal-backdrop')) {
        ReuseHubModal.close(e.target);
      }
    });

    // 2. Keyboard accessibility (Escape key and Tab focus trap)
    document.addEventListener('keydown', function (e) {
      if (!ReuseHubModal.activeModal) return;

      if (e.key === 'Escape' || e.key === 'Esc') {
        e.preventDefault();
        ReuseHubModal.close(ReuseHubModal.activeModal);
        return;
      }

      if (e.key === 'Tab') {
        const modal = ReuseHubModal.activeModal;
        const focusables = Array.from(modal.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ));
        if (focusables.length === 0) return;

        const first = focusables[0];
        const last = focusables[focusables.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    });

    // 3. Dynamic setup for Delete Listing buttons in listings table
    document.addEventListener('click', function (e) {
      const deleteBtn = e.target.closest('.delete-listing-btn, [data-delete-modal]');
      if (!deleteBtn) return;

      e.preventDefault();
      const title = deleteBtn.getAttribute('data-item-title') || 'this item';
      const actionUrl = deleteBtn.getAttribute('data-delete-url') || deleteBtn.getAttribute('href');

      const modal = document.getElementById('deleteListingModal') || document.getElementById('deleteItemModal');
      if (!modal) {
        // Fallback to direct navigation if modal markup is not on page
        if (actionUrl) window.location.href = actionUrl;
        return;
      }

      // Update modal title text & form action
      const titleEl = modal.querySelector('#deleteItemTitleDisplay');
      if (titleEl) {
        titleEl.textContent = title;
      }

      const formEl = modal.querySelector('form');
      if (formEl && actionUrl) {
        formEl.setAttribute('action', actionUrl);
      }

      ReuseHubModal.open(modal);
    });
  });
})();
