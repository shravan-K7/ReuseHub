/**
 * ReuseHub - Comprehensive Client-Side Form Validation Engine
 * Provides instant real-time feedback and clear inline error messages across all forms:
 * - Login & Registration forms (with password show/hide toggle)
 * - Item listing create / edit form
 * - Item request form (donor contact coordination)
 * - Listing report form
 * - User profile edit form
 * - Admin category creation form
 * 
 * Rules:
 * 1. If user submits a form leaving any required field blank/invalid, JavaScript displays
 *    a clear error message directly below the corresponding input field and prevents submission.
 * 2. As soon as the user starts typing or correcting the information, the error message
 *    automatically disappears immediately without page reload.
 * 
 * document.querySelector() is a built-in DOM method used to find and select the first HTML element that matches one or more specified CSS selectors
 */

window.ReuseHubValidationLoaded = true;

document.addEventListener('DOMContentLoaded', function () {
  initPasswordToggles();
  initLoginForm();
  initRegisterForm();
  initPasswordResetForm();
  initOtpForm();
  initSetNewPasswordForm();
  initItemForm();
  initItemRequestForm();
  initReportForm();
  initProfileForm();
  initCategoryForm();
  initUniversalFormValidation();
});

function markFormBound(form) {
  if (!form) return false;
  if (form.getAttribute('data-validation-bound') === 'true') return false;
  form.setAttribute('data-validation-bound', 'true');
  return true;
}

// ==============================================================================
// 1. INLINE ERROR UTILITIES
// ==============================================================================
function showFieldError(input, message) {
  if (!input) return;

  const formGroup = input.closest('.form-group') || input.parentElement;
  if (!formGroup) return;

  input.classList.add('input-error');

  // Determine where to place the error message (after input wrappers if present)
  let anchor = input;
  const wrapper =
    input.closest('.location-search-wrapper') ||
    input.closest('.password-input-wrap') ||
    input.closest('.input-wrapper');
  if (wrapper) {
    anchor = wrapper;
  }

  // Check if error message element already exists
  let errorEl = formGroup.querySelector('.field-error-msg');
  if (!errorEl) {
    errorEl = document.createElement('div');
    errorEl.className = 'field-error-msg';

    if (anchor.nextSibling) {
      anchor.parentNode.insertBefore(errorEl, anchor.nextSibling);
    } else {
      anchor.parentNode.appendChild(errorEl);
    }
  }

  // Update content with clear warning icon and text
  errorEl.innerHTML = `
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="8" x2="12" y2="12"></line>
      <line x1="12" y1="16" x2="12.01" y2="16"></line>
    </svg>
    <span>${message}</span>
  `;
}

function clearFieldError(input) {
  if (!input) return;

  input.classList.remove('input-error');
  const formGroup = input.closest('.form-group') || input.parentElement;
  if (!formGroup) return;

  const errorEls = formGroup.querySelectorAll('.field-error-msg, .form-error-msg');
  errorEls.forEach(function (el) {
    el.remove();
  });
}

// Attach real-time clear listeners to remove error as soon as user types or selects
function attachRealtimeClear(input, validatorFn) {
  if (!input) return;

  const eventType = (input.tagName === 'SELECT' || input.type === 'file' || input.type === 'checkbox')
    ? 'change'
    : 'input';

  input.addEventListener(eventType, function () {
    if (typeof validatorFn === 'function') {
      if (validatorFn(input)) {
        clearFieldError(input);
      }
    } else {
      if (input.type === 'checkbox') {
        clearFieldError(input);
      } else if (input.value && input.value.trim().length > 0) {
        clearFieldError(input);
      }
    }
  });
}

// ==============================================================================
// 2. PASSWORD SHOW / HIDE TOGGLE
// ==============================================================================
function initPasswordToggles() {
  const toggleButtons = document.querySelectorAll('.password-toggle-btn');

  toggleButtons.forEach(function (button) {
    if (button.dataset.toggleBound === 'true') return;
    button.dataset.toggleBound = 'true';

    button.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();

      const targetId = button.getAttribute('data-target');
      const input = targetId
        ? document.getElementById(targetId)
        : button.closest('.password-input-wrap')?.querySelector('input');

      if (!input) return;

      const eyeOpen = button.querySelector('.eye-open');
      const eyeClosed = button.querySelector('.eye-closed');
      const isPassword = input.getAttribute('type') === 'password' || input.type === 'password';

      if (isPassword) {
        input.setAttribute('type', 'text');
        input.type = 'text';
        if (eyeOpen) eyeOpen.style.display = 'none';
        if (eyeClosed) eyeClosed.style.display = 'block';
        button.setAttribute('aria-label', 'Hide password');
        button.title = 'Hide password';
      } else {
        input.setAttribute('type', 'password');
        input.type = 'password';
        if (eyeOpen) eyeOpen.style.display = 'block';
        if (eyeClosed) eyeClosed.style.display = 'none';
        button.setAttribute('aria-label', 'Show password');
        button.title = 'Show password';
      }

      const len = input.value.length;
      input.focus();
      try {
        input.setSelectionRange(len, len);
      } catch (err) {
        // Ignored if unsupported
      }
    });
  });
}

// ==============================================================================
// 3. LOGIN FORM VALIDATION
// ==============================================================================
function initLoginForm() {
  const form = document.getElementById('loginForm');
  if (!form) return;
  if (!markFormBound(form)) return;

  const usernameInput = form.querySelector('input[name="username"]');
  const passwordInput = form.querySelector('input[name="password"]');
  if (!usernameInput || !passwordInput) return;

  form.setAttribute('novalidate', 'true');

  attachRealtimeClear(usernameInput);
  attachRealtimeClear(passwordInput);

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!usernameInput || !usernameInput.value.trim()) {
      showFieldError(usernameInput, 'Please enter your username.');
      isValid = false;
      if (!firstInvalid) firstInvalid = usernameInput;
    } else {
      clearFieldError(usernameInput);
    }

    if (!passwordInput || !passwordInput.value) {
      showFieldError(passwordInput, 'Please enter your password.');
      isValid = false;
      if (!firstInvalid) firstInvalid = passwordInput;
    } else {
      clearFieldError(passwordInput);
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 4. REGISTRATION FORM VALIDATION
// ==============================================================================
function initRegisterForm() {
  const form = document.getElementById('registerForm');
  if (!form) return;
  if (!markFormBound(form)) return;

  const usernameInput = form.querySelector('input[name="username"]');
  const emailInput = form.querySelector('input[name="email"]');
  const passwordInput = form.querySelector('input[name="password"]');
  const confirmPasswordInput = form.querySelector('input[name="confirm_password"]');
  if (!usernameInput || !emailInput || !passwordInput || !confirmPasswordInput) return;

  form.setAttribute('novalidate', 'true');

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function validateUsername(silent = false) {
    if (!usernameInput) return true;
    const val = usernameInput.value.trim();
    if (!val) {
      if (!silent) showFieldError(usernameInput, 'Please choose a username.');
      return false;
    }
    if (val.length < 3) {
      if (!silent) showFieldError(usernameInput, 'Username must be at least 3 characters.');
      return false;
    }
    clearFieldError(usernameInput);
    return true;
  }

  function validateEmail(silent = false) {
    if (!emailInput) return true;
    const val = emailInput.value.trim();
    if (!val) {
      if (!silent) showFieldError(emailInput, 'Please enter your email address.');
      return false;
    }
    if (!emailRegex.test(val)) {
      if (!silent) showFieldError(emailInput, 'Please enter a valid email address.');
      return false;
    }
    clearFieldError(emailInput);
    return true;
  }

  function validatePassword(silent = false) {
    if (!passwordInput) return true;
    const val = passwordInput.value;
    if (!val) {
      if (!silent) showFieldError(passwordInput, 'Please create a password.');
      return false;
    }
    if (val.length < 8) {
      if (!silent) showFieldError(passwordInput, 'Password must be at least 8 characters long.');
      return false;
    }
    clearFieldError(passwordInput);

    if (confirmPasswordInput && confirmPasswordInput.value.length > 0) {
      validateConfirmPassword(false);
    }
    return true;
  }

  function validateConfirmPassword(silent = false) {
    if (!confirmPasswordInput) return true;
    const confirmVal = confirmPasswordInput.value;
    const passVal = passwordInput ? passwordInput.value : '';

    if (!confirmVal) {
      if (!silent) showFieldError(confirmPasswordInput, 'Please confirm your password.');
      return false;
    }
    if (confirmVal !== passVal) {
      if (!silent) showFieldError(confirmPasswordInput, 'Passwords do not match.');
      return false;
    }
    clearFieldError(confirmPasswordInput);
    return true;
  }

  // Real-time clearing
  if (usernameInput) {
    usernameInput.addEventListener('input', function () {
      if (usernameInput.value.trim().length >= 3) clearFieldError(usernameInput);
    });
  }
  if (emailInput) {
    emailInput.addEventListener('input', function () {
      if (emailRegex.test(emailInput.value.trim())) clearFieldError(emailInput);
    });
  }
  if (passwordInput) {
    passwordInput.addEventListener('input', function () {
      if (passwordInput.value.length >= 8) clearFieldError(passwordInput);
      if (confirmPasswordInput && confirmPasswordInput.value === passwordInput.value) {
        clearFieldError(confirmPasswordInput);
      }
    });
  }
  if (confirmPasswordInput) {
    confirmPasswordInput.addEventListener('input', function () {
      if (passwordInput && confirmPasswordInput.value === passwordInput.value) {
        clearFieldError(confirmPasswordInput);
      }
    });
  }

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!validateUsername(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = usernameInput;
    }
    if (!validateEmail(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = emailInput;
    }
    if (!validatePassword(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = passwordInput;
    }
    if (!validateConfirmPassword(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = confirmPasswordInput;
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 4B. PASSWORD RESET FORM VALIDATION
// ==============================================================================
function initPasswordResetForm() {
  const form = document.getElementById('passwordResetForm');
  if (!form) return;
  if (!markFormBound(form)) return;

  form.setAttribute('novalidate', 'true');
  const emailInput = form.querySelector('input[name="email"]');
  if (!emailInput) return;

  const submitBtn = form.querySelector('button[type="submit"]');
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function validateEmail(silent = false) {
    const val = emailInput.value.trim();
    if (!val) {
      if (!silent) showFieldError(emailInput, 'Please enter your registered email address.');
      return false;
    }
    if (!emailRegex.test(val)) {
      if (!silent) showFieldError(emailInput, 'Please enter a valid email address (e.g. name@example.com).');
      return false;
    }
    clearFieldError(emailInput);
    return true;
  }

  attachRealtimeClear(emailInput);
  emailInput.addEventListener('blur', function () {
    if (emailInput.value.trim()) {
      validateEmail(false);
    }
  });

  form.addEventListener('submit', function (e) {
    if (!validateEmail(false)) {
      e.preventDefault();
      emailInput.focus();
      emailInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="submit-spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #ffffff;border-top-color:transparent;border-radius:50%;margin-right:8px;vertical-align:middle;animation:spin 0.8s linear infinite;"></span> Sending Reset Email...';
      }
    }
  });
}

// ==============================================================================
// 4C. EMAIL OTP VERIFICATION FORM VALIDATION
// ==============================================================================
function initOtpForm() {
  const form = document.getElementById('otpForm');
  if (!form) return;
  if (!markFormBound(form)) return;

  form.setAttribute('novalidate', 'true');
  const otpInput = form.querySelector('input[name="otp"]');
  if (!otpInput) return;

  const submitBtn = form.querySelector('button[type="submit"]');

  function validateOtp(silent = false) {
    const val = otpInput.value.trim();
    if (!val) {
      if (!silent) showFieldError(otpInput, 'Please enter the 6-digit verification code.');
      return false;
    }
    if (!/^\d{6}$/.test(val)) {
      if (!silent) showFieldError(otpInput, 'Verification code must be exactly 6 digits.');
      return false;
    }
    clearFieldError(otpInput);
    return true;
  }

  attachRealtimeClear(otpInput);

  form.addEventListener('submit', function (e) {
    if (!validateOtp(false)) {
      e.preventDefault();
      otpInput.focus();
      otpInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="submit-spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #ffffff;border-top-color:transparent;border-radius:50%;margin-right:8px;vertical-align:middle;animation:spin 0.8s linear infinite;"></span> Verifying Code...';
      }
    }
  });
}

// ==============================================================================
// 4D. SET NEW PASSWORD FORM VALIDATION
// ==============================================================================
function initSetNewPasswordForm() {
  const form = document.getElementById('setNewPasswordForm');
  if (!form) return;
  if (!markFormBound(form)) return;

  form.setAttribute('novalidate', 'true');
  const p1 = form.querySelector('input[name="new_password1"]');
  const p2 = form.querySelector('input[name="new_password2"]');
  if (!p1 || !p2) return;

  const submitBtn = form.querySelector('button[type="submit"]');

  attachRealtimeClear(p1);
  attachRealtimeClear(p2);

  function validateNewPassword(silent = false) {
    const val = p1.value;
    if (!val) {
      if (!silent) showFieldError(p1, 'Please enter a new password.');
      return false;
    }
    if (val.length < 8) {
      if (!silent) showFieldError(p1, 'Password must be at least 8 characters long.');
      return false;
    }
    clearFieldError(p1);
    return true;
  }

  function validateConfirmPassword(silent = false) {
    const val2 = p2.value;
    const val1 = p1.value;
    if (!val2) {
      if (!silent) showFieldError(p2, 'Please confirm your new password.');
      return false;
    }
    if (val1 !== val2) {
      if (!silent) showFieldError(p2, 'Passwords do not match.');
      return false;
    }
    clearFieldError(p2);
    return true;
  }

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!validateNewPassword(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = p1;
    }
    if (!validateConfirmPassword(false)) {
      isValid = false;
      if (!firstInvalid) firstInvalid = p2;
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="submit-spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #ffffff;border-top-color:transparent;border-radius:50%;margin-right:8px;vertical-align:middle;animation:spin 0.8s linear infinite;"></span> Updating Password...';
      }
    }
  });
}

// ==============================================================================
// 5. ITEM LISTING CREATE / EDIT FORM VALIDATION
// ==============================================================================
function initItemForm() {
  const form = document.querySelector('.item-form-card form') || document.querySelector('form[enctype="multipart/form-data"]:has(#id_title)');
  if (!form) return;

  form.setAttribute('novalidate', 'true');

  const titleInput = form.querySelector('#id_title') || form.querySelector('input[name="title"]');
  const categorySelect = form.querySelector('#id_category') || form.querySelector('select[name="category"]');
  const conditionSelect = form.querySelector('#id_condition') || form.querySelector('select[name="condition"]');
  const locationInput = form.querySelector('#id_pickup_location') || form.querySelector('input[name="pickup_location"]');
  const descInput = form.querySelector('#id_description') || form.querySelector('textarea[name="description"]');
  const repairCheck = form.querySelector('#id_is_repairable') || form.querySelector('input[name="is_repairable"]');
  const repairDetailsInput = form.querySelector('#id_repair_details') || form.querySelector('textarea[name="repair_details"]');
  const imageInput = form.querySelector('#id_images') || form.querySelector('#id_image') || form.querySelector('input[type="file"]');
  const previewContainer = form.querySelector('#newImagesPreviewContainer');
  const limitBadge = form.querySelector('#photoLimitBadge');
  const deleteCheckboxes = form.querySelectorAll('.delete-photo-checkbox');
  const coverChoiceInput = form.querySelector('#coverChoiceInput');

  function getExistingCount() {
    let count = 0;
    const cards = form.querySelectorAll('.existing-photo-card');
    cards.forEach(card => {
      const chk = card.querySelector('.delete-photo-checkbox');
      if (!chk || !chk.checked) count++;
    });
    return count;
  }

  function updateLimitBadge() {
    if (!limitBadge) return;
    const existing = getExistingCount();
    const newlySelected = imageInput && imageInput.files ? imageInput.files.length : 0;
    const total = existing + newlySelected;
    limitBadge.textContent = `${total}/5 photos`;
    if (total > 5) {
      limitBadge.style.color = '#ef4444';
      limitBadge.style.background = 'rgba(239, 68, 68, 0.1)';
      limitBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
    } else {
      limitBadge.style.color = '';
      limitBadge.style.background = '';
      limitBadge.style.borderColor = '';
    }
  }

  function setCoverChoice(choice) {
    if (coverChoiceInput) {
      coverChoiceInput.value = choice;
    }
    syncCoverSelection();
  }

  function syncCoverSelection() {
    if (!coverChoiceInput) return;
    let current = coverChoiceInput.value;

    // Collect all valid/active choices (existing non-deleted + new preview cards)
    const availableChoices = [];

    form.querySelectorAll('.existing-photo-card').forEach(card => {
      const chk = card.querySelector('.delete-photo-checkbox');
      const isDeleted = chk && chk.checked;
      const choice = card.dataset.choice;
      if (!isDeleted && choice) {
        availableChoices.push(choice);
      }
    });

    if (previewContainer) {
      previewContainer.querySelectorAll('.preview-photo-card').forEach(card => {
        const choice = card.dataset.choice;
        if (choice) {
          availableChoices.push(choice);
        }
      });
    }

    // If current choice is no longer available or was deleted, fall back
    if (!availableChoices.includes(current)) {
      if (availableChoices.length > 0) {
        current = availableChoices[0];
        coverChoiceInput.value = current;
      } else {
        current = 'new:0';
        coverChoiceInput.value = current;
      }
    }

    // Synchronize existing photo cards UI
    form.querySelectorAll('.existing-photo-card').forEach(card => {
      const choice = card.dataset.choice;
      const btn = card.querySelector('.set-cover-btn');
      const chk = card.querySelector('.delete-photo-checkbox');
      const isDeleted = chk && chk.checked;
      const isSelected = (!isDeleted && choice === current);

      if (isSelected) {
        card.classList.add('is-cover');
        if (btn) {
          btn.classList.add('active');
          btn.textContent = '★ Cover';
        }
      } else {
        card.classList.remove('is-cover');
        if (btn) {
          btn.classList.remove('active');
          btn.textContent = 'Make Cover';
        }
      }
    });

    // Synchronize preview photo cards UI
    if (previewContainer) {
      previewContainer.querySelectorAll('.preview-photo-card').forEach(card => {
        const choice = card.dataset.choice;
        const btn = card.querySelector('.set-cover-btn');
        const isSelected = (choice === current);

        if (isSelected) {
          card.classList.add('is-cover');
          if (btn) {
            btn.classList.add('active');
            btn.textContent = '★ Cover';
          }
        } else {
          card.classList.remove('is-cover');
          if (btn) {
            btn.classList.remove('active');
            btn.textContent = 'Make Cover';
          }
        }
      });
    }
  }

  // Bind clicks on existing photo cards
  form.querySelectorAll('.existing-photo-card').forEach(card => {
    const btn = card.querySelector('.set-cover-btn');
    const choice = card.dataset.choice;

    if (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        setCoverChoice(choice);
      });
    }

    card.addEventListener('click', function (e) {
      if (e.target.closest('.delete-photo-toggle')) return;
      const chk = card.querySelector('.delete-photo-checkbox');
      if (chk && chk.checked) return;
      setCoverChoice(choice);
    });
  });

  if (deleteCheckboxes.length > 0) {
    deleteCheckboxes.forEach(chk => {
      chk.addEventListener('change', function () {
        const card = chk.closest('.existing-photo-card');
        if (card) {
          if (chk.checked) {
            card.classList.add('marked-deleted');
          } else {
            card.classList.remove('marked-deleted');
          }
        }
        updateLimitBadge();
        syncCoverSelection();
        validateImages();
      });
    });
  }

  function validateImages() {
    if (!imageInput) return true;
    const files = imageInput.files ? Array.from(imageInput.files) : [];
    const existingCount = getExistingCount();
    const total = existingCount + files.length;

    if (total > 5) {
      showFieldError(imageInput, `You can upload at most 5 images in total (currently ${existingCount} active + ${files.length} selected = ${total}).`);
      return false;
    }

    const validExtensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif'];
    const validMimes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      const isValidExt = validExtensions.includes(ext);
      const isValidMime = !f.type || validMimes.includes(f.type) || f.type.startsWith('image/');

      if (!isValidExt) {
        showFieldError(imageInput, `'${f.name}' has an unsupported format. Allowed formats: JPEG (.jpg, .jpeg), PNG (.png), WebP (.webp), and GIF (.gif).`);
        return false;
      }

      if (f.size > 10 * 1024 * 1024) {
        const sizeMb = (f.size / (1024 * 1024)).toFixed(1);
        showFieldError(imageInput, `'${f.name}' exceeds the 10MB limit (size: ${sizeMb}MB).`);
        return false;
      }
    }

    clearFieldError(imageInput);
    return true;
  }

  function renderPreviews() {
    if (!previewContainer || !imageInput) return;
    previewContainer.innerHTML = '';
    const files = imageInput.files ? Array.from(imageInput.files) : [];

    if (files.length === 0) {
      previewContainer.style.display = 'none';
      syncCoverSelection();
      return;
    }

    previewContainer.style.display = 'grid';
    files.forEach((file, idx) => {
      const choiceVal = `new:${idx}`;
      const card = document.createElement('div');
      card.className = 'preview-photo-card';
      card.dataset.choice = choiceVal;

      const img = document.createElement('img');
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      card.appendChild(img);

      // Make Cover button
      const coverBtn = document.createElement('button');
      coverBtn.type = 'button';
      coverBtn.className = 'set-cover-btn';
      coverBtn.dataset.choice = choiceVal;
      coverBtn.title = 'Click to make this the cover photo';
      coverBtn.textContent = 'Make Cover';
      coverBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        setCoverChoice(choiceVal);
      });
      card.appendChild(coverBtn);

      // Remove photo button
      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'preview-photo-remove-btn';
      removeBtn.innerHTML = '&times;';
      removeBtn.title = 'Remove this photo';
      removeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        const dt = new DataTransfer();
        Array.from(imageInput.files).forEach((f, fIdx) => {
          if (fIdx !== idx) dt.items.add(f);
        });
        imageInput.files = dt.files;
        renderPreviews();
        updateLimitBadge();
        validateImages();
      });
      card.appendChild(removeBtn);

      // Clicking card selects cover
      card.addEventListener('click', function (e) {
        if (e.target.closest('.preview-photo-remove-btn')) return;
        setCoverChoice(choiceVal);
      });

      previewContainer.appendChild(card);
    });

    syncCoverSelection();
  }

  if (imageInput) {
    imageInput.addEventListener('change', function () {
      renderPreviews();
      updateLimitBadge();
      validateImages();
    });
  }

  // Initial synchronization for existing photos & limit badge
  updateLimitBadge();
  syncCoverSelection();

  // Real-time clearing
  attachRealtimeClear(titleInput);
  attachRealtimeClear(categorySelect);
  attachRealtimeClear(conditionSelect);
  attachRealtimeClear(locationInput);
  attachRealtimeClear(descInput);
  attachRealtimeClear(repairDetailsInput);

  if (repairCheck && repairDetailsInput) {
    repairCheck.addEventListener('change', function () {
      if (!repairCheck.checked) {
        clearFieldError(repairDetailsInput);
      }
    });
  }

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    // Validate images (max 5, types, sizes)
    if (!validateImages()) {
      isValid = false;
      if (!firstInvalid) firstInvalid = imageInput;
    }

    // 1. Title validation
    if (!titleInput || !titleInput.value.trim()) {
      showFieldError(titleInput, 'Please enter a descriptive item title.');
      isValid = false;
      if (!firstInvalid) firstInvalid = titleInput;
    } else if (titleInput.value.trim().length < 3) {
      showFieldError(titleInput, 'Title must be at least 3 characters long.');
      isValid = false;
      if (!firstInvalid) firstInvalid = titleInput;
    } else {
      clearFieldError(titleInput);
    }

    // 2. Category validation
    if (!categorySelect || !categorySelect.value) {
      showFieldError(categorySelect, 'Please select a category for this item.');
      isValid = false;
      if (!firstInvalid) firstInvalid = categorySelect;
    } else {
      clearFieldError(categorySelect);
    }

    // 3. Condition validation
    if (!conditionSelect || !conditionSelect.value) {
      showFieldError(conditionSelect, 'Please select the item condition.');
      isValid = false;
      if (!firstInvalid) firstInvalid = conditionSelect;
    } else {
      clearFieldError(conditionSelect);
    }

    // 4. Pickup Location validation
    if (!locationInput || !locationInput.value.trim()) {
      showFieldError(locationInput, 'Please enter or select a convenient pickup location.');
      isValid = false;
      if (!firstInvalid) firstInvalid = locationInput;
    } else {
      clearFieldError(locationInput);
    }

    // 5. Description validation
    if (!descInput || !descInput.value.trim()) {
      showFieldError(descInput, 'Please provide helpful details about the item in the description.');
      isValid = false;
      if (!firstInvalid) firstInvalid = descInput;
    } else if (descInput.value.trim().length < 10) {
      showFieldError(descInput, 'Description should be at least 10 characters long.');
      isValid = false;
      if (!firstInvalid) firstInvalid = descInput;
    } else {
      clearFieldError(descInput);
    }

    // 6. Repair Details (only required if is_repairable checkbox is checked)
    if (repairCheck && repairCheck.checked) {
      if (!repairDetailsInput || !repairDetailsInput.value.trim()) {
        showFieldError(repairDetailsInput, 'Please explain what needs repair or restoration.');
        isValid = false;
        if (!firstInvalid) firstInvalid = repairDetailsInput;
      } else {
        clearFieldError(repairDetailsInput);
      }
    } else if (repairDetailsInput) {
      clearFieldError(repairDetailsInput);
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 6. ITEM REQUEST FORM VALIDATION (on item_detail.html)
// ==============================================================================
function initItemRequestForm() {
  const form = document.querySelector('form[action*="request"]') || document.querySelector('.action-card form:has(#id_message)');
  if (!form) return;

  form.setAttribute('novalidate', 'true');
  const messageInput = form.querySelector('#id_message') || form.querySelector('textarea[name="message"]');
  const contactInput = form.querySelector('#id_contact_info') || form.querySelector('input[name="contact_info"]');

  attachRealtimeClear(messageInput);
  attachRealtimeClear(contactInput);

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!messageInput || !messageInput.value.trim()) {
      showFieldError(messageInput, "Please write a message to the donor explaining why you'd like this item.");
      isValid = false;
      if (!firstInvalid) firstInvalid = messageInput;
    } else if (messageInput.value.trim().length < 5) {
      showFieldError(messageInput, 'Message should be at least 5 characters long.');
      isValid = false;
      if (!firstInvalid) firstInvalid = messageInput;
    } else {
      clearFieldError(messageInput);
    }

    if (!contactInput || !contactInput.value.trim()) {
      showFieldError(contactInput, 'Please provide your contact details (phone, WhatsApp, or handle) for coordination.');
      isValid = false;
      if (!firstInvalid) firstInvalid = contactInput;
    } else {
      clearFieldError(contactInput);
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 7. REPORT LISTING FORM VALIDATION
// ==============================================================================
function initReportForm() {
  const form = document.querySelector('.report-card form') || document.querySelector('form:has(#id_reason)');
  if (!form) return;

  form.setAttribute('novalidate', 'true');
  const reasonSelect = form.querySelector('#id_reason') || form.querySelector('select[name="reason"]');
  const detailsInput = form.querySelector('#id_details') || form.querySelector('textarea[name="details"]');

  attachRealtimeClear(reasonSelect);
  attachRealtimeClear(detailsInput);

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!reasonSelect || !reasonSelect.value) {
      showFieldError(reasonSelect, 'Please select a reason for reporting this listing.');
      isValid = false;
      if (!firstInvalid) firstInvalid = reasonSelect;
    } else {
      clearFieldError(reasonSelect);
    }

    if (!detailsInput || !detailsInput.value.trim()) {
      showFieldError(detailsInput, 'Please provide details explaining why you are reporting this listing.');
      isValid = false;
      if (!firstInvalid) firstInvalid = detailsInput;
    } else if (detailsInput.value.trim().length < 10) {
      showFieldError(detailsInput, 'Please provide at least 10 characters of context.');
      isValid = false;
      if (!firstInvalid) firstInvalid = detailsInput;
    } else {
      clearFieldError(detailsInput);
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 8. USER PROFILE EDIT FORM VALIDATION
// ==============================================================================
function initProfileForm() {
  const form = document.querySelector('.profile-container form');
  if (!form) return;

  form.setAttribute('novalidate', 'true');
  const phoneInput = form.querySelector('#id_phone') || form.querySelector('input[name="phone"]');

  if (phoneInput) {
    attachRealtimeClear(phoneInput, function (el) {
      const val = el.value.trim();
      return !val || /^[+0-9\s\-()]{7,20}$/.test(val);
    });
  }

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (phoneInput && phoneInput.value.trim()) {
      const phoneVal = phoneInput.value.trim();
      const phoneRegex = /^[+0-9\s\-()]{7,20}$/;
      if (!phoneRegex.test(phoneVal)) {
        showFieldError(phoneInput, 'Please enter a valid phone number (digits, spaces, or plus sign).');
        isValid = false;
        if (!firstInvalid) firstInvalid = phoneInput;
      } else {
        clearFieldError(phoneInput);
      }
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 9. ADMIN CATEGORY FORM VALIDATION
// ==============================================================================
function initCategoryForm() {
  const form = document.querySelector('.admin-categories-container .action-card form') || document.querySelector('form:has(#id_name)');
  if (!form) return;

  form.setAttribute('novalidate', 'true');
  const nameInput = form.querySelector('#id_name') || form.querySelector('input[name="name"]');

  attachRealtimeClear(nameInput);

  form.addEventListener('submit', function (e) {
    let isValid = true;
    let firstInvalid = null;

    if (!nameInput || !nameInput.value.trim()) {
      showFieldError(nameInput, 'Please enter a category name.');
      isValid = false;
      if (!firstInvalid) firstInvalid = nameInput;
    } else if (nameInput.value.trim().length < 2) {
      showFieldError(nameInput, 'Category name must be at least 2 characters long.');
      isValid = false;
      if (!firstInvalid) firstInvalid = nameInput;
    } else {
      clearFieldError(nameInput);
    }

    if (!isValid) {
      e.preventDefault();
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  });
}

// ==============================================================================
// 10. UNIVERSAL GENERIC FALLBACK FOR ANY OTHER FORMS
// ==============================================================================
function initUniversalFormValidation() {
  const forms = document.querySelectorAll('form:not([data-validated])');

  forms.forEach(function (form) {
    // Avoid double-binding specifically initialized forms
    if (
      form.getAttribute('data-validation-bound') === 'true' ||
      form.id === 'passwordResetForm' ||
      form.id === 'otpForm' ||
      form.id === 'resendForm' ||
      form.id === 'setNewPasswordForm' ||
      form.id === 'loginForm' ||
      form.id === 'registerForm' ||
      form.closest('.item-form-card') ||
      form.closest('.report-card') ||
      form.closest('.profile-container') ||
      form.closest('.admin-categories-container') ||
      form.querySelector('#id_message')
    ) {
      return;
    }

    // Find any inputs marked required or with required attribute
    const requiredInputs = form.querySelectorAll('input[required], select[required], textarea[required]');
    if (requiredInputs.length === 0) return;

    form.setAttribute('novalidate', 'true');
    form.setAttribute('data-validated', 'true');

    requiredInputs.forEach(function (input) {
      attachRealtimeClear(input);
    });

    form.addEventListener('submit', function (e) {
      let isValid = true;
      let firstInvalid = null;

      requiredInputs.forEach(function (input) {
        const val = input.value ? input.value.trim() : '';
        if (!val) {
          const label = input.closest('.form-group')?.querySelector('label')?.textContent?.replace('*', '').trim() || 'This field';
          showFieldError(input, `${label} is required.`);
          isValid = false;
          if (!firstInvalid) firstInvalid = input;
        } else {
          clearFieldError(input);
        }
      });

      if (!isValid) {
        e.preventDefault();
        if (firstInvalid) {
          firstInvalid.focus();
          firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    });
  });
}
