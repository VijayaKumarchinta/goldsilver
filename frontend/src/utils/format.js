const enIN = new Intl.NumberFormat('en-IN');
const enIN2 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const enIN0 = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });

export function parseDateTime(value) {
  if (value === null || value === undefined || value === '') return null;
  let normalized = String(value).trim().replace(' ', 'T');
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    normalized += 'T00:00:00Z';
  } else if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)) {
    normalized += 'Z';
  }
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function money(amount, decimals = 2) {
  const formatter = decimals === 0 ? enIN0 : enIN2;
  return '₹' + formatter.format(amount);
}

export function moneyRaw(amount, decimals = 2) {
  const n = decimals === 0 ? Math.round(amount) : amount;
  return '₹' + (decimals === 0 ? enIN0.format(Math.round(amount)) : enIN2.format(amount));
}

export function pct(value) {
  const sign = value >= 0 ? '▲' : '▼';
  return `${sign} ${Math.abs(value).toFixed(2)}%`;
}

export function pctSigned(value) {
  const sign = value >= 0 ? '+' : '\u2212';
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

export function formatDate(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata' });
}

export function formatDateTime(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
    hour12: false,
  });
}

export function formatTime(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
    hour12: false,
  });
}

export function formatFullDate(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'Asia/Kolkata',
  });
}

export function formatDayMonth(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    timeZone: 'Asia/Kolkata',
  });
}

export function dayOfWeek(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return '—';
  return d.toLocaleDateString('en-IN', {
    weekday: 'short',
    timeZone: 'Asia/Kolkata',
  });
}

export function isWeekend(utcIso) {
  const d = parseDateTime(utcIso);
  if (!d) return false;
  const day = d.getUTCDay();
  return day === 0 || day === 6;
}
