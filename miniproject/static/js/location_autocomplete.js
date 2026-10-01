/**
 * ReuseHub - Location Search & Autocomplete via OpenStreetMap Nominatim
 * Enforces English-only results (&accept-language=en and English sanitization)
 * Provides real-time suggestions for the pickup-location field, captures coordinates,
 * and syncs with hidden latitude/longitude fields without requiring Leaflet.
 */

document.addEventListener('DOMContentLoaded', function () {
  const locationInput = document.getElementById('id_pickup_location');
  const latInput = document.getElementById('id_latitude');
  const lngInput = document.getElementById('id_longitude');
  const suggestionsBox = document.getElementById('locationSuggestions');
  const spinner = document.getElementById('locationSearchSpinner');
  const clearBtn = document.getElementById('btnClearLocation');
  const locateBtn = document.getElementById('btnLocateMe');
  const selectedBadge = document.getElementById('selectedLocationBadge');
  const selectedPlaceText = document.getElementById('selectedPlaceText');
  const selectedCoordsText = document.getElementById('selectedCoordsText');
  const btnRemoveLocation = document.getElementById('btnRemoveLocation');

  if (!locationInput) return;

  // Enhance input attributes
  locationInput.setAttribute('autocomplete', 'off');
  locationInput.setAttribute('placeholder', 'e.g. Badiyadka, Jaipur, Indiranagar...');

  let debounceTimer = null;
  let currentController = null;
  let activeIndex = -1;
  let currentItems = [];

  // Helper to check if string contains only Latin/English characters, digits, spaces, and punctuation
  function isEnglishOnly(str) {
    if (!str) return true;
    return /^[\u0000-\u007F\u00C0-\u024F\s.,'()/\-]+$/.test(str.trim());
  }

  // Filter out any non-English/non-Latin segments from a comma-separated string
  function filterEnglishSegments(str) {
    if (!str) return '';
    const parts = str.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    const englishParts = parts.filter(function (p) { return isEnglishOnly(p); });
    return englishParts.length > 0 ? englishParts.join(', ') : '';
  }

  // Check if coordinates already exist (Edit Item mode)
  if (latInput && latInput.value && lngInput && lngInput.value) {
    showSelectedBadge(
      locationInput.value || 'Saved Location',
      parseFloat(latInput.value),
      parseFloat(lngInput.value)
    );
  }

  // Input event with 300ms debounce
  locationInput.addEventListener('input', function () {
    const query = locationInput.value.trim();

    // Toggle clear button
    if (clearBtn) {
      clearBtn.style.display = query.length > 0 ? 'inline-flex' : 'none';
    }

    clearTimeout(debounceTimer);

    if (query.length < 2) {
      hideSuggestions();
      return;
    }

    debounceTimer = setTimeout(function () {
      fetchSuggestions(query);
    }, 300);
  });

  // Clear button click
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      locationInput.value = '';
      clearBtn.style.display = 'none';
      hideSuggestions();
      locationInput.focus();
    });
  }

  // Remove confirmed badge & clear coordinates
  if (btnRemoveLocation) {
    btnRemoveLocation.addEventListener('click', function () {
      if (latInput) latInput.value = '';
      if (lngInput) lngInput.value = '';
      if (selectedBadge) selectedBadge.style.display = 'none';
      locationInput.focus();
    });
  }

  // Keyboard navigation
  locationInput.addEventListener('keydown', function (e) {
    if (!suggestionsBox || suggestionsBox.style.display === 'none') return;

    const items = suggestionsBox.querySelectorAll('.suggestion-item');
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % items.length;
      updateActiveItem(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + items.length) % items.length;
      updateActiveItem(items);
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0 && activeIndex < currentItems.length) {
        e.preventDefault();
        selectSuggestion(currentItems[activeIndex]);
      }
    } else if (e.key === 'Escape') {
      hideSuggestions();
    }
  });

  function updateActiveItem(items) {
    items.forEach(function (el, idx) {
      if (idx === activeIndex) {
        el.classList.add('active');
        el.scrollIntoView({ block: 'nearest' });
      } else {
        el.classList.remove('active');
      }
    });
  }

  // Close suggestions when clicking outside
  document.addEventListener('click', function (e) {
    if (!locationInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
      hideSuggestions();
    }
  });

  // Fetch suggestions from OpenStreetMap Nominatim with English language enforcement
  function fetchSuggestions(query) {
    if (currentController) {
      currentController.abort();
    }
    currentController = new AbortController();

    if (spinner) spinner.style.display = 'inline-block';

    // Explicitly enforce accept-language=en and request namedetails
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&addressdetails=1&namedetails=1&limit=6&accept-language=en`;

    fetch(url, {
      headers: {
        'Accept': 'application/json',
        'Accept-Language': 'en, en-US;q=0.9'
      },
      signal: currentController.signal
    })
      .then(function (response) {
        if (!response.ok) throw new Error('Search failed');
        return response.json();
      })
      .then(function (data) {
        if (spinner) spinner.style.display = 'none';
        currentItems = data || [];
        renderSuggestions(currentItems, query);
      })
      .catch(function (err) {
        if (err.name === 'AbortError') return;
        if (spinner) spinner.style.display = 'none';
        console.warn('Nominatim search error:', err);
      });
  }

  // Render suggestion list
  function renderSuggestions(items, query) {
    if (!suggestionsBox) return;

    suggestionsBox.innerHTML = '';
    activeIndex = -1;

    if (!items || items.length === 0) {
      suggestionsBox.innerHTML = `
        <div class="suggestion-empty">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <span>No matching locations found for "${escapeHtml(query)}"</span>
        </div>
      `;
      suggestionsBox.style.display = 'block';
      return;
    }

    const listContainer = document.createElement('div');
    listContainer.className = 'suggestions-list';

    items.forEach(function (item, index) {
      const parsed = parseNominatimItem(item);

      const itemEl = document.createElement('div');
      itemEl.className = 'suggestion-item';
      itemEl.setAttribute('role', 'option');
      itemEl.setAttribute('data-index', index);

      itemEl.innerHTML = `
        <div class="suggestion-icon">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
            <circle cx="12" cy="10" r="3"></circle>
          </svg>
        </div>
        <div class="suggestion-content">
          <div class="suggestion-main">${escapeHtml(parsed.main)}</div>
          <div class="suggestion-sub">${escapeHtml(parsed.sub)}</div>
        </div>
        <div class="suggestion-coords">
          ${parseFloat(item.lat).toFixed(4)}, ${parseFloat(item.lon).toFixed(4)}
        </div>
      `;

      itemEl.addEventListener('click', function () {
        selectSuggestion(item);
      });

      itemEl.addEventListener('mouseenter', function () {
        activeIndex = index;
        updateActiveItem(listContainer.querySelectorAll('.suggestion-item'));
      });

      listContainer.appendChild(itemEl);
    });

    suggestionsBox.appendChild(listContainer);

    // Subtle footer attribution
    const footer = document.createElement('div');
    footer.className = 'suggestions-footer';
    footer.innerHTML = `
      <span>Location search powered by OpenStreetMap Nominatim (English)</span>
    `;
    suggestionsBox.appendChild(footer);

    suggestionsBox.style.display = 'block';
  }

  // Parse Nominatim response into English main place name and secondary location context
  function parseNominatimItem(item) {
    const namedetails = item.namedetails || {};
    const addr = item.address || {};

    // 1. Prefer explicit English name from namedetails
    let main =
      namedetails['name:en'] ||
      namedetails['int_name'] ||
      namedetails['alt_name:en'] ||
      '';

    // 2. Check address components for clean English candidates
    if (!main) {
      const candidates = [
        addr.town,
        addr.village,
        addr.suburb,
        addr.neighbourhood,
        addr.city,
        addr.county,
        addr.road,
        item.name
      ];
      for (let i = 0; i < candidates.length; i++) {
        if (candidates[i] && isEnglishOnly(candidates[i])) {
          main = candidates[i];
          break;
        }
      }
    }

    // 3. Fall back to first segment of display_name if English
    if (!main) {
      const firstSegment = (item.display_name || '').split(',')[0].trim();
      if (isEnglishOnly(firstSegment)) {
        main = firstSegment;
      } else {
        main = addr.state || addr.country || 'Location';
      }
    }

    // Context components (city, county, state, postcode, country)
    const rawContext = [
      namedetails['city:en'] || addr.city,
      namedetails['county:en'] || addr.county,
      namedetails['state:en'] || addr.state,
      addr.postcode,
      namedetails['country:en'] || addr.country
    ];

    const contextParts = rawContext.filter(function (part, idx, self) {
      return (
        part &&
        isEnglishOnly(part) &&
        part !== main &&
        self.indexOf(part) === idx
      );
    });

    let sub = contextParts.join(', ');

    // If sub is still empty, clean display_name of any non-English text
    if (!sub && item.display_name) {
      sub = filterEnglishSegments(item.display_name);
    }

    return {
      main: main,
      sub: sub,
      fullTitle: sub ? `${main}, ${sub}` : main
    };
  }

  // Select a suggestion
  function selectSuggestion(item) {
    const parsed = parseNominatimItem(item);
    const chosenName = parsed.fullTitle || filterEnglishSegments(item.display_name) || item.display_name;
    const lat = parseFloat(item.lat);
    const lng = parseFloat(item.lon);

    locationInput.value = chosenName;

    if (latInput) latInput.value = lat.toFixed(6);
    if (lngInput) lngInput.value = lng.toFixed(6);

    showSelectedBadge(chosenName, lat, lng);
    hideSuggestions();

    if (clearBtn) clearBtn.style.display = 'inline-flex';
  }

  // Display confirmed location coordinates pill
  function showSelectedBadge(placeName, lat, lng) {
    if (!selectedBadge) return;

    if (selectedPlaceText) {
      selectedPlaceText.textContent = placeName;
    }
    if (selectedCoordsText) {
      selectedCoordsText.textContent = `Coordinates: ${lat.toFixed(6)}, ${lng.toFixed(6)}`;
    }

    selectedBadge.style.display = 'flex';
  }

  function hideSuggestions() {
    if (suggestionsBox) {
      suggestionsBox.style.display = 'none';
      suggestionsBox.innerHTML = '';
    }
    activeIndex = -1;
  }

  // "Use My Current Location" via Browser Geolocation & Nominatim Reverse Geocoding in English
  if (locateBtn) {
    locateBtn.addEventListener('click', function () {
      if (!navigator.geolocation) {
        alert('Geolocation is not supported by your browser.');
        return;
      }

      const originalText = locateBtn.innerHTML;
      locateBtn.disabled = true;
      locateBtn.innerHTML = `
        <span class="location-spinner inline-spinner"></span>
        <span>Locating...</span>
      `;

      navigator.geolocation.getCurrentPosition(
        function (pos) {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;

          // Reverse geocode via Nominatim with English language enforcement
          const reverseUrl = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&accept-language=en`;

          fetch(reverseUrl, {
            headers: {
              'Accept': 'application/json',
              'Accept-Language': 'en, en-US;q=0.9'
            }
          })
            .then(function (res) { return res.json(); })
            .then(function (data) {
              locateBtn.disabled = false;
              locateBtn.innerHTML = originalText;

              let placeName = '';
              if (data && data.address) {
                const addr = data.address;
                const locality = [
                  addr.suburb,
                  addr.neighbourhood,
                  addr.road,
                  addr.quarter,
                  addr.town,
                  addr.village
                ].find(function (val) {
                  return val && isEnglishOnly(val);
                }) || '';

                const city = [
                  addr.city,
                  addr.county,
                  addr.state,
                  addr.country
                ].filter(function (val) {
                  return val && isEnglishOnly(val);
                }).join(', ');

                placeName = [locality, city].filter(Boolean).join(', ');
              }

              if (!placeName && data && data.display_name) {
                placeName = filterEnglishSegments(data.display_name);
              }

              if (!placeName) {
                placeName = `Location near ${lat.toFixed(4)}, ${lng.toFixed(4)}`;
              }

              locationInput.value = placeName;
              if (latInput) latInput.value = lat.toFixed(6);
              if (lngInput) lngInput.value = lng.toFixed(6);

              showSelectedBadge(placeName, lat, lng);
              if (clearBtn) clearBtn.style.display = 'inline-flex';
            })
            .catch(function (err) {
              locateBtn.disabled = false;
              locateBtn.innerHTML = originalText;

              const fallbackName = `GPS Location (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
              locationInput.value = fallbackName;
              if (latInput) latInput.value = lat.toFixed(6);
              if (lngInput) lngInput.value = lng.toFixed(6);
              showSelectedBadge(fallbackName, lat, lng);
            });
        },
        function (err) {
          locateBtn.disabled = false;
          locateBtn.innerHTML = originalText;
          alert('Could not determine current location: ' + err.message);
        },
        { timeout: 10000, enableHighAccuracy: true }
      );
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
