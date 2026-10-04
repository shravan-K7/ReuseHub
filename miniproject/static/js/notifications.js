/**
 * ReuseHub - Simplified Notification Engine
 */
(function () {
  'use strict';

  const user = document.body ? document.body.getAttribute('data-current-user') : null;
  if (!user) return;

  const KEY = 'reusehub_notifications_' + user;

  function getNotifs() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || '[]');
    } catch (e) {
      return [];
    }
  }

  function saveNotifs(list) {
    localStorage.setItem(KEY, JSON.stringify(list));
    updateBadge();
  }

  function addNotif(item) {
    const list = getNotifs();
    if (item.sourceId && list.some(function (n) { return n.sourceId === item.sourceId; })) return;
    list.unshift({
      id: 'n_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
      type: item.type || 'system',
      title: item.title,
      message: item.message,
      link: item.link || '',
      linkText: item.linkText || 'View Details',
      badge: item.badge || 'Update',
      read: false,
      timestamp: item.timestamp || Date.now(),
      sourceId: item.sourceId || null
    });
    saveNotifs(list);
  }

  function updateBadge() {
    const unread = getNotifs().filter(function (n) { return !n.read; }).length;
    const badges = document.querySelectorAll('#navNotificationBadge, .admin-bell-badge');
    badges.forEach(function (b) {
      b.textContent = unread > 99 ? '99+' : unread;
      b.style.display = unread > 0 ? 'inline-flex' : 'none';
    });
  }

  function timeAgo(ts) {
    const time = typeof ts === 'number' ? ts : new Date(ts).getTime();
    const sec = Math.floor((Date.now() - time) / 1000);
    if (sec < 60) return 'Just now';
    if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
    if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
    if (sec < 172800) return 'Yesterday';
    return Math.floor(sec / 86400) + 'd ago';
  }

  function syncServer() {
    const script = document.getElementById('serverNotificationData');
    if (!script) return;
    try {
      const data = JSON.parse(script.textContent);
      (data.incoming_requests || []).forEach(function (r) {
        if (r.status === 'PENDING') {
          addNotif({
            sourceId: 'req_' + r.id,
            type: 'request_received',
            badge: 'Item Request',
            title: 'New Request for "' + r.item__title + '"',
            message: '@' + r.requester__username + ' requested to claim your item "' + r.item__title + '".',
            link: '/items/' + r.item_id + '/',
            linkText: 'Review Request',
            timestamp: r.created_at
          });
        }
      });
      (data.outgoing_requests || []).forEach(function (r) {
        if (r.status === 'ACCEPTED') {
          addNotif({
            sourceId: 'req_acc_' + r.id,
            type: 'request_accepted',
            badge: 'Accepted',
            title: 'Request Accepted: "' + r.item__title + '"',
            message: 'Great news! @' + r.item__donor__username + ' accepted your request for "' + r.item__title + '".',
            link: '/items/' + r.item_id + '/',
            linkText: 'Pickup Info',
            timestamp: r.updated_at
          });
        } else if (r.status === 'REJECTED') {
          addNotif({
            sourceId: 'req_rej_' + r.id,
            type: 'request_declined',
            badge: 'Declined',
            title: 'Request Update: "' + r.item__title + '"',
            message: '@' + r.item__donor__username + ' declined your request for "' + r.item__title + '".',
            link: '/home/',
            linkText: 'Browse Items',
            timestamp: r.updated_at
          });
        }
      });
      (data.moderated_items || []).forEach(function (m) {
        if (m.moderation_status === 'APPROVED') {
          addNotif({
            sourceId: 'mod_app_' + m.id,
            type: 'moderator_mail',
            badge: 'Moderator Mail',
            title: 'Listing Approved: "' + m.title + '"',
            message: 'Mail from Moderator: Your listing "' + m.title + '" was approved by moderation.',
            link: '/items/' + m.id + '/',
            linkText: 'View Listing',
            timestamp: m.created_at
          });
        } else if (m.moderation_status === 'FLAGGED') {
          addNotif({
            sourceId: 'mod_flag_' + m.id,
            type: 'moderator_mail',
            badge: 'Moderator Notice',
            title: 'Listing Under Review: "' + m.title + '"',
            message: 'Notice from Moderator: Your listing "' + m.title + '" was flagged for review.',
            link: '/items/' + m.id + '/',
            linkText: 'Check Listing',
            timestamp: m.created_at
          });
        }
      });
    } catch (e) {}
  }

  function purgeMockNotifications() {
    const list = getNotifs();
    const cleaned = list.filter(function (n) {
      if (n.id === 's2' || n.id === 's3') return false;
      if (!n.sourceId && (n.title === 'New Request on your listing' || n.title === 'Request Accepted!')) return false;
      return true;
    });
    if (cleaned.length !== list.length) {
      saveNotifs(cleaned);
    }
  }

  function seedInitial() {
    const seedKey = 'reusehub_seeded_' + user;
    if (localStorage.getItem(seedKey)) return;
    localStorage.setItem(seedKey, '1');
    if (getNotifs().length === 0) {
      saveNotifs([
        {
          id: 's1',
          type: 'moderator_mail',
          badge: 'Moderator Mail',
          title: 'Welcome to ReuseHub!',
          message: 'Mail from Moderator Team: Thank you for joining. Help neighbors choose reuse and repair.',
          link: '/about/',
          linkText: 'Read Guidelines',
          timestamp: Date.now(),
          read: false
        }
      ]);
    }
  }

  function renderPage(filter) {
    filter = filter || 'all';
    const container = document.getElementById('notificationsListContainer');
    const empty = document.getElementById('notificationsEmptyState');
    if (!container) return;

    const all = getNotifs();
    const unreadCount = all.filter(function (n) { return !n.read; }).length;

    const setTxt = function (id, val) {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };
    setTxt('countFilterAll', all.length);
    setTxt('countFilterUnread', unreadCount);
    setTxt('countFilterRequests', all.filter(function (n) { return n.type.indexOf('request_') === 0; }).length);
    setTxt('countFilterMod', all.filter(function (n) { return n.type === 'moderator_mail'; }).length);

    const pill = document.getElementById('unreadHeaderPill');
    if (pill) {
      pill.textContent = unreadCount + ' unread';
      pill.style.display = unreadCount > 0 ? 'inline-flex' : 'none';
    }

    let items = all;
    if (filter === 'unread') items = all.filter(function (n) { return !n.read; });
    else if (filter === 'requests') items = all.filter(function (n) { return n.type.indexOf('request_') === 0; });
    else if (filter === 'moderator') items = all.filter(function (n) { return n.type === 'moderator_mail'; });

    if (items.length === 0) {
      container.innerHTML = '';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';

    const icons = {
      request_received: { cls: 'icon-request', bCls: 'badge-req', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>' },
      request_accepted: { cls: 'icon-accepted', bCls: 'badge-acc', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>' },
      request_declined: { cls: 'icon-declined', bCls: 'badge-dec', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>' },
      moderator_mail: { cls: 'icon-moderator', bCls: 'badge-mod', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>' }
    };
    const defaultIcon = { cls: 'icon-system', bCls: 'badge-sys', svg: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>' };

    container.innerHTML = items.map(function (n) {
      const ic = icons[n.type] || defaultIcon;
      return '<article class="notif-card ' + (n.read ? 'read' : 'unread') + '" data-id="' + n.id + '">' +
        '<div class="notif-card-side">' +
          '<div class="notif-icon-bubble ' + ic.cls + '">' + ic.svg + '</div>' +
          (!n.read ? '<span class="notif-unread-dot"></span>' : '') +
        '</div>' +
        '<div class="notif-card-main">' +
          '<div class="notif-card-header">' +
            '<div class="notif-badge-wrap">' +
              '<span class="notif-type-tag ' + ic.bCls + '">' + (n.badge || 'Update') + '</span>' +
              '<span class="notif-time">' + timeAgo(n.timestamp) + '</span>' +
            '</div>' +
            '<div class="notif-card-actions">' +
              '<button type="button" class="notif-action-btn toggle-read" title="' + (n.read ? 'Mark unread' : 'Mark read') + '">' +
                (n.read 
                  ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle></svg>'
                  : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>') +
              '</button>' +
              '<button type="button" class="notif-action-btn delete-notif" title="Delete">' +
                '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>' +
              '</button>' +
            '</div>' +
          '</div>' +
          '<h3 class="notif-title">' + n.title + '</h3>' +
          '<p class="notif-message">' + n.message + '</p>' +
          (n.link ? '<div class="notif-link-wrap"><a href="' + n.link + '" class="notif-link-btn"><span>' + n.linkText + '</span> &rarr;</a></div>' : '') +
        '</div>' +
      '</article>';
    }).join('');

    container.querySelectorAll('.notif-card').forEach(function (card) {
      const id = card.getAttribute('data-id');
      const toggle = card.querySelector('.toggle-read');
      if (toggle) {
        toggle.addEventListener('click', function (e) {
          e.stopPropagation();
          const list = getNotifs();
          const t = list.find(function (n) { return n.id === id; });
          if (t) {
            t.read = !t.read;
            saveNotifs(list);
            renderPage(filter);
          }
        });
      }
      const del = card.querySelector('.delete-notif');
      if (del) {
        del.addEventListener('click', function (e) {
          e.stopPropagation();
          saveNotifs(getNotifs().filter(function (n) { return n.id !== id; }));
          renderPage(filter);
        });
      }
      card.addEventListener('click', function (e) {
        if (e.target.closest('a, button')) return;
        const list = getNotifs();
        const t = list.find(function (n) { return n.id === id; });
        if (t && !t.read) {
          t.read = true;
          saveNotifs(list);
          renderPage(filter);
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    purgeMockNotifications();
    seedInitial();
    syncServer();
    updateBadge();

    const root = document.getElementById('notificationsPageRoot');
    if (!root) return;

    let currentFilter = 'all';
    document.querySelectorAll('.notif-filter-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.notif-filter-tab').forEach(function (t) { t.classList.remove('active'); });
        this.classList.add('active');
        currentFilter = this.getAttribute('data-filter') || 'all';
        renderPage(currentFilter);
      });
    });

    const markAll = document.getElementById('markAllReadBtn');
    if (markAll) {
      markAll.addEventListener('click', function () {
        const list = getNotifs();
        list.forEach(function (n) { n.read = true; });
        saveNotifs(list);
        renderPage(currentFilter);
      });
    }


    renderPage('all');
  });

  window.addEventListener('storage', function (e) {
    if (e.key === KEY) {
      updateBadge();
      renderPage();
    }
  });

  window.NotificationHub = {
    add: addNotif,
    getUnreadCount: function () {
      return getNotifs().filter(function (n) { return !n.read; }).length;
    },
    refresh: updateBadge
  };
})();
