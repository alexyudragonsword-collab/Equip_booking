/* Timeline visual grid: render, selection, booking */

const CSRF = () => document.querySelector('meta[name="csrf-token"]').content;

// ===== Render pass =====
function renderGrid() {
  document.querySelectorAll('.slot').forEach(cell => {
    const instrId = cell.dataset.instrument;
    const dateStr  = cell.dataset.date;
    const hour     = parseInt(cell.dataset.hour, 10);

    // Remove previous state classes
    cell.classList.remove('slot-available', 'slot-booked', 'slot-booked-mine', 'slot-past', 'slot-selecting');
    cell.innerHTML = '';
    cell.title = '';
    cell.onmousedown = null;
    cell.onmouseover = null;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const cellDate = new Date(dateStr + 'T00:00:00');

    // Past cell (date before today, or today but hour already passed)
    const isPast = cellDate < today ||
      (cellDate.getTime() === today.getTime() && hour < new Date().getHours());

    if (isPast) {
      cell.classList.add('slot-past');
      return;
    }

    const instrBookings = (BOOKINGS_DATA[instrId] || {})[dateStr] || [];
    const booking = instrBookings.find(b => b.start_hour <= hour && hour < b.end_hour);

    if (booking) {
      const isMine = booking.user_id === CURRENT_USER_ID;
      cell.classList.add(isMine ? 'slot-booked-mine' : 'slot-booked');
      cell.title = `${booking.user_name}: ${booking.start_hour}:00 – ${booking.end_hour}:00`;
      // Show initials label only on the first hour of the booking
      if (hour === booking.start_hour) {
        const initials = booking.user_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        const label = document.createElement('div');
        label.className = 'slot-label';
        label.textContent = initials;
        cell.appendChild(label);
      }
    } else {
      cell.classList.add('slot-available');
      cell.onmousedown = e => startSelection(e, cell);
    }
  });
}

// ===== Selection state =====
let sel = {
  active: false,
  instrumentId: null,
  date: null,
  startHour: null,
  endHour: null,
  cells: [],
};

function startSelection(e, cell) {
  if (e.button !== 0) return;  // left click only; ignore right/middle
  e.preventDefault();
  clearSelection();

  sel.active = true;
  sel.instrumentId = cell.dataset.instrument;
  sel.date = cell.dataset.date;
  sel.startHour = parseInt(cell.dataset.hour, 10);
  sel.endHour = sel.startHour + 1;
  sel.cells = [cell];

  cell.classList.remove('slot-available');
  cell.classList.add('slot-selecting');
}

document.addEventListener('mouseover', e => {
  if (!sel.active) return;
  const cell = e.target.closest('.slot');
  if (!cell) return;
  if (cell.dataset.instrument !== sel.instrumentId) return;
  if (cell.dataset.date !== sel.date) return;

  const hour = parseInt(cell.dataset.hour, 10);
  if (hour <= sel.startHour) return; // Only extend forward

  const newEndHour = hour + 1;
  const duration = newEndHour - sel.startHour;
  if (duration > 4) return; // Max 4 hours

  // Check all intermediate cells are available
  for (let h = sel.startHour; h < newEndHour; h++) {
    const c = findCell(sel.instrumentId, sel.date, h);
    if (!c) return;
    const instrBookings = (BOOKINGS_DATA[sel.instrumentId] || {})[sel.date] || [];
    const booked = instrBookings.find(b => b.start_hour <= h && h < b.end_hour);
    if (booked) return;
  }

  // Update selection
  sel.cells.forEach(c => {
    c.classList.remove('slot-selecting');
    c.classList.add('slot-available');
  });
  sel.cells = [];
  sel.endHour = newEndHour;

  for (let h = sel.startHour; h < sel.endHour; h++) {
    const c = findCell(sel.instrumentId, sel.date, h);
    if (c) {
      c.classList.remove('slot-available');
      c.classList.add('slot-selecting');
      sel.cells.push(c);
    }
  }
});

document.addEventListener('mouseup', e => {
  if (!sel.active) return;
  sel.active = false;

  if (!sel.cells.length) return;

  const lastCell = sel.cells[sel.cells.length - 1];
  _popoverJustShown = true;   // suppress the click event that immediately follows
  showPopover(lastCell);
});

let _popoverJustShown = false;

document.addEventListener('click', e => {
  if (_popoverJustShown) {
    _popoverJustShown = false;
    return;  // this click is the tail of the mousedown→mouseup that showed the popover
  }
  const popover = document.getElementById('bookingPopover');
  if (!popover.contains(e.target)) {
    hidePopover();
  }
});

function clearSelection() {
  sel.cells.forEach(c => {
    c.classList.remove('slot-selecting');
    c.classList.add('slot-available');
  });
  sel = { active: false, instrumentId: null, date: null, startHour: null, endHour: null, cells: [] };
}

function findCell(instrId, dateStr, hour) {
  return document.querySelector(
    `.slot[data-instrument="${instrId}"][data-date="${dateStr}"][data-hour="${hour}"]`
  );
}

// ===== Popover =====
function showPopover(anchorCell) {
  const popover = document.getElementById('bookingPopover');
  const instrName = document.querySelector(`[data-instrument="${sel.instrumentId}"] .grid-card-header`)?.textContent ||
                    document.querySelector(`.timeline-table[data-instrument="${sel.instrumentId}"]`)
                             ?.closest('.grid-card')?.querySelector('.grid-card-header')?.textContent || 'Instrument';

  const dateObj = new Date(sel.date + 'T00:00:00');
  const dateFmt = dateObj.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });

  document.getElementById('popoverText').textContent =
    `Book ${instrName} on ${dateFmt} from ${pad(sel.startHour)}:00 to ${pad(sel.endHour)}:00 (${sel.endHour - sel.startHour}h)?`;

  const rect = anchorCell.getBoundingClientRect();
  popover.style.display = 'block';
  popover.style.top = (window.scrollY + rect.bottom + 8) + 'px';
  popover.style.left = Math.min(rect.left, window.innerWidth - 360) + 'px';
}

function hidePopover() {
  document.getElementById('bookingPopover').style.display = 'none';
  clearSelection();
}

document.getElementById('btnConfirmBook').addEventListener('click', () => {
  const payload = {
    instrument_id: sel.instrumentId,
    date: sel.date,
    start_hour: sel.startHour,
    end_hour: sel.endHour,
  };
  hidePopover();
  submitBooking(payload, 'statusMsg');
});

document.getElementById('btnCancelBook').addEventListener('click', () => {
  hidePopover();
});

// ===== Booking submit =====
function submitBooking(payload, statusElId) {
  fetch('/book', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': CSRF(),
    },
    body: JSON.stringify(payload),
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      const b = data.booking;
      const instrBookings = BOOKINGS_DATA[String(payload.instrument_id)] ||= {};
      const dateBookings  = instrBookings[payload.date] ||= [];
      dateBookings.push(b);
      renderGrid();
      showStatus(statusElId, `Booked ${pad(b.start_hour)}:00–${pad(b.end_hour)}:00 successfully.`, 'success');
    } else {
      showStatus(statusElId, data.error || 'Booking failed.', 'danger');
    }
  })
  .catch(() => showStatus(statusElId, 'Network error. Please try again.', 'danger'));
}

// ===== Mode toggle =====
function setMode(mode) {
  const visual = document.getElementById('visualSection');
  const form   = document.getElementById('formSection');
  const btnV   = document.getElementById('btnVisual');
  const btnF   = document.getElementById('btnForm');
  if (mode === 'visual') {
    visual.style.display = '';
    form.style.display   = 'none';
    btnV.classList.add('active');
    btnF.classList.remove('active');
  } else {
    visual.style.display = 'none';
    form.style.display   = '';
    btnV.classList.remove('active');
    btnF.classList.add('active');
  }
}

// ===== Helpers =====
function pad(h) { return String(h).padStart(2, '0'); }

function showStatus(elId, msg, type) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = msg;
  el.className = `status-msg status-${type}`;
  el.style.display = 'block';
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.style.display = 'none'; }, 5000);
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  renderGrid();
});
