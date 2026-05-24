/* Form-based booking: dropdown wiring + submit */

document.addEventListener('DOMContentLoaded', () => {
  const fInstrument = document.getElementById('fInstrument');
  const fDate       = document.getElementById('fDate');
  const fStart      = document.getElementById('fStart');
  const fEnd        = document.getElementById('fEnd');
  const btnBook     = document.getElementById('btnFormBook');

  if (!fInstrument) return; // page doesn't have form section

  // Restrict max date for non-admins
  if (!IS_ADMIN) {
    fDate.max = MAX_BOOKING_DATE;
  }

  // Disable weekends in date input via JS (HTML min/max can't block weekends)
  fDate.addEventListener('input', () => {
    const d = new Date(fDate.value + 'T00:00:00');
    if (d.getDay() === 0 || d.getDay() === 6) {
      fDate.setCustomValidity('Weekend dates cannot be booked. Please select a weekday.');
      fDate.reportValidity();
      fDate.value = '';
    } else {
      fDate.setCustomValidity('');
    }
    rebuildEndTimes();
  });

  fInstrument.addEventListener('change', rebuildEndTimes);
  fStart.addEventListener('change', rebuildEndTimes);

  function getAvailability(instrId, dateStr) {
    return ((BOOKINGS_DATA[instrId] || {})[dateStr] || []);
  }

  function isHourFree(instrId, dateStr, hour) {
    const bookings = getAvailability(instrId, dateStr);
    return !bookings.find(b => b.start_hour <= hour && hour < b.end_hour);
  }

  function rebuildEndTimes() {
    fEnd.innerHTML = '<option value="">— End —</option>';
    fEnd.disabled = true;

    const instrId   = fInstrument.value;
    const dateStr   = fDate.value;
    const startHour = parseInt(fStart.value, 10);

    if (!instrId || !dateStr || isNaN(startHour)) return;

    // Check start hour is free
    if (!isHourFree(instrId, dateStr, startHour)) {
      fStart.setCustomValidity('This start time overlaps with an existing booking.');
      return;
    }
    fStart.setCustomValidity('');

    // Build end times: startHour+1 .. min(startHour+4, 17), stopping at first booked hour
    for (let endHour = startHour + 1; endHour <= Math.min(startHour + 4, 17); endHour++) {
      // Check the hour before endHour is free
      if (!isHourFree(instrId, dateStr, endHour - 1)) break;
      const opt = document.createElement('option');
      opt.value = endHour;
      opt.textContent = `${String(endHour).padStart(2, '0')}:00`;
      fEnd.appendChild(opt);
    }

    if (fEnd.options.length > 1) {
      fEnd.disabled = false;
    }
  }

  btnBook.addEventListener('click', () => {
    const instrId   = fInstrument.value;
    const dateStr   = fDate.value;
    const startHour = parseInt(fStart.value, 10);
    const endHour   = parseInt(fEnd.value, 10);

    if (!instrId || !dateStr || isNaN(startHour) || isNaN(endHour)) {
      showFormStatus('Please fill in all fields.', 'danger');
      return;
    }

    const payload = {
      instrument_id: instrId,
      date: dateStr,
      start_hour: startHour,
      end_hour: endHour,
    };

    btnBook.disabled = true;
    fetch('/book', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
      },
      body: JSON.stringify(payload),
    })
    .then(r => r.json())
    .then(data => {
      btnBook.disabled = false;
      if (data.success) {
        const b = data.booking;
        const instrBookings = BOOKINGS_DATA[instrId] ||= {};
        const dateBookings  = instrBookings[dateStr] ||= [];
        dateBookings.push(b);

        // Reset form
        fInstrument.value = '';
        fDate.value = '';
        fStart.value = '';
        fEnd.innerHTML = '<option value="">— End —</option>';
        fEnd.disabled = true;

        showFormStatus(`Booked ${String(b.start_hour).padStart(2,'0')}:00–${String(b.end_hour).padStart(2,'0')}:00 successfully.`, 'success');
      } else {
        showFormStatus(data.error || 'Booking failed.', 'danger');
      }
    })
    .catch(() => {
      btnBook.disabled = false;
      showFormStatus('Network error. Please try again.', 'danger');
    });
  });

  function showFormStatus(msg, type) {
    const el = document.getElementById('formStatus');
    el.textContent = msg;
    el.className = `status-msg status-${type}`;
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(() => el.style.display = 'none', 5000);
  }
});
