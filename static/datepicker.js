/* ═══════════════════════════════════════════════════
   Custom Date Picker — Glassmorphism Dark Theme
   JavaScript Component
   ═══════════════════════════════════════════════════ */

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];
const MONTH_SHORT = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
];
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

class GlassDatePicker {
    constructor(triggerEl, hiddenInput, options = {}) {
        this.triggerEl = triggerEl;
        this.hiddenInput = hiddenInput;
        this.options = options;
        this.isOpen = false;
        this.viewMode = 'days'; // days | months | years

        this.selectedDate = this._parseValue(hiddenInput.value);
        this.viewDate = new Date(
            this.selectedDate.getFullYear(),
            this.selectedDate.getMonth(),
            1
        );

        this.container = null;
        this.overlay = null;

        this._updateDisplay();
        this._bindTrigger();
    }

    _parseValue(val) {
        if (!val) return new Date();
        const parts = val.split('-');
        if (parts.length === 3) {
            return new Date(+parts[0], +parts[1] - 1, +parts[2]);
        }
        return new Date();
    }

    _formatDate(d) {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const yyyy = d.getFullYear();
        return `${dd}-${mm}-${yyyy}`;
    }

    _formatISO(d) {
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        return `${d.getFullYear()}-${mm}-${dd}`;
    }

    _updateDisplay() {
        const textEl = this.triggerEl.querySelector('.date-display__text');
        if (textEl) {
            textEl.textContent = this._formatDate(this.selectedDate);
        }
    }

    _bindTrigger() {
        this.triggerEl.addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.isOpen) {
                this.close();
            } else {
                this.open();
            }
        });
    }

    open() {
        if (this.isOpen) return;
        this.isOpen = true;
        this.viewMode = 'days';
        this.triggerEl.classList.add('active');

        this.overlay = document.createElement('div');
        this.overlay.className = 'dp-overlay';
        this.overlay.addEventListener('click', () => this.close());

        this.container = document.createElement('div');
        this.container.className = 'dp-container';
        this.container.addEventListener('click', (e) => e.stopPropagation());

        const rect = this.triggerEl.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;

        if (spaceBelow >= 360 || spaceBelow >= spaceAbove) {
            this.container.style.top = `${rect.bottom + 6}px`;
        } else {
            this.container.style.bottom = `${window.innerHeight - rect.top + 6}px`;
        }
        this.container.style.left = `${rect.left}px`;

        document.body.appendChild(this.overlay);
        document.body.appendChild(this.container);

        this._render();
    }

    close() {
        if (!this.isOpen) return;
        this.isOpen = false;
        this.triggerEl.classList.remove('active');
        if (this.overlay) this.overlay.remove();
        if (this.container) this.container.remove();
        this.overlay = null;
        this.container = null;
    }

    _render() {
        if (!this.container) return;
        switch (this.viewMode) {
            case 'days':   this._renderDays(); break;
            case 'months': this._renderMonths(); break;
            case 'years':  this._renderYears(); break;
        }
    }

    _renderDays() {
        const year = this.viewDate.getFullYear();
        const month = this.viewDate.getMonth();
        const today = new Date();

        let html = `<div class="dp-header">
            <span class="dp-title" id="dp-title-click">${MONTH_NAMES[month]} ${year}</span>
            <div class="dp-nav">
                <button class="dp-nav-btn" data-action="prev-month">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="15 18 9 12 15 6"/></svg>
                </button>
                <button class="dp-nav-btn" data-action="next-month">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="9 6 15 12 9 18"/></svg>
                </button>
            </div>
        </div>`;

        html += '<div class="dp-weekdays">';
        for (const wd of WEEKDAYS) {
            html += `<span class="dp-weekday">${wd}</span>`;
        }
        html += '</div>';

        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const daysInPrevMonth = new Date(year, month, 0).getDate();

        html += '<div class="dp-days">';

        for (let i = 0; i < firstDay; i++) {
            const day = daysInPrevMonth - firstDay + 1 + i;
            html += `<button class="dp-day dp-day--other-month" data-day="${day}" data-month="${month - 1}" data-year="${year}">${day}</button>`;
        }

        for (let d = 1; d <= daysInMonth; d++) {
            let classes = 'dp-day';
            const isToday = d === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const isSelected = d === this.selectedDate.getDate()
                && month === this.selectedDate.getMonth()
                && year === this.selectedDate.getFullYear();

            if (isToday) classes += ' dp-day--today';
            if (isSelected) classes += ' dp-day--selected';

            html += `<button class="${classes}" data-day="${d}" data-month="${month}" data-year="${year}">${d}</button>`;
        }

        const totalCells = firstDay + daysInMonth;
        const remaining = 42 - totalCells;
        for (let i = 1; i <= remaining; i++) {
            html += `<button class="dp-day dp-day--other-month" data-day="${i}" data-month="${month + 1}" data-year="${year}">${i}</button>`;
        }

        html += '</div>';

        html += `<div class="dp-footer">
            <button class="dp-footer-btn dp-footer-btn--clear" data-action="clear">Clear</button>
            <button class="dp-footer-btn dp-footer-btn--today" data-action="today">Today</button>
        </div>`;

        this.container.innerHTML = html;
        this._bindDayEvents();
    }

    _bindDayEvents() {
        this.container.querySelector('#dp-title-click').addEventListener('click', () => {
            this.viewMode = 'months';
            this._render();
        });

        this.container.querySelectorAll('.dp-nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                if (action === 'prev-month') {
                    this.viewDate.setMonth(this.viewDate.getMonth() - 1);
                } else if (action === 'next-month') {
                    this.viewDate.setMonth(this.viewDate.getMonth() + 1);
                }
                this._render();
            });
        });

        this.container.querySelectorAll('.dp-day:not(.dp-day--disabled):not(.dp-day--empty)').forEach(btn => {
            btn.addEventListener('click', () => {
                let m = parseInt(btn.dataset.month);
                let y = parseInt(btn.dataset.year);
                const d = parseInt(btn.dataset.day);
                if (m < 0) { m = 11; y--; }
                if (m > 11) { m = 0; y++; }
                this.selectedDate = new Date(y, m, d);
                this.hiddenInput.value = this._formatISO(this.selectedDate);
                this._updateDisplay();
                this.close();
                this.hiddenInput.dispatchEvent(new Event('change'));
            });
        });

        this.container.querySelectorAll('.dp-footer-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                if (action === 'today') {
                    const now = new Date();
                    this.selectedDate = now;
                    this.viewDate = new Date(now.getFullYear(), now.getMonth(), 1);
                    this.hiddenInput.value = this._formatISO(this.selectedDate);
                    this._updateDisplay();
                    this.close();
                    this.hiddenInput.dispatchEvent(new Event('change'));
                } else if (action === 'clear') {
                    this.hiddenInput.value = '';
                    const textEl = this.triggerEl.querySelector('.date-display__text');
                    if (textEl) textEl.textContent = 'Select date';
                    this.close();
                }
            });
        });
    }

    _renderMonths() {
        const year = this.viewDate.getFullYear();
        const currentMonth = new Date().getMonth();
        const currentYear = new Date().getFullYear();

        let html = `<div class="dp-header">
            <span class="dp-title" id="dp-title-click">${year}</span>
            <div class="dp-nav">
                <button class="dp-nav-btn" data-action="prev-year">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="15 18 9 12 15 6"/></svg>
                </button>
                <button class="dp-nav-btn" data-action="next-year">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="9 6 15 12 9 18"/></svg>
                </button>
            </div>
        </div>`;

        html += '<div class="dp-month-grid">';
        for (let m = 0; m < 12; m++) {
            let cls = 'dp-month-btn';
            if (m === currentMonth && year === currentYear) cls += ' dp-month-btn--current';
            if (m === this.viewDate.getMonth() && year === this.viewDate.getFullYear()) cls += ' dp-month-btn--selected';
            html += `<button class="${cls}" data-month="${m}">${MONTH_SHORT[m]}</button>`;
        }
        html += '</div>';

        html += `<div class="dp-footer">
            <button class="dp-footer-btn dp-footer-btn--clear" data-action="back-years">← Years</button>
            <span></span>
        </div>`;

        this.container.innerHTML = html;

        this.container.querySelector('#dp-title-click').addEventListener('click', () => {
            this.viewMode = 'years';
            this._render();
        });

        this.container.querySelectorAll('.dp-nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.dataset.action === 'prev-year') this.viewDate.setFullYear(this.viewDate.getFullYear() - 1);
                else this.viewDate.setFullYear(this.viewDate.getFullYear() + 1);
                this._render();
            });
        });

        this.container.querySelectorAll('.dp-month-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.viewDate.setMonth(parseInt(btn.dataset.month));
                this.viewMode = 'days';
                this._render();
            });
        });

        const backBtn = this.container.querySelector('[data-action="back-years"]');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                this.viewMode = 'years';
                this._render();
            });
        }
    }

    _renderYears() {
        const currentYear = new Date().getFullYear();
        const selectedYear = this.viewDate.getFullYear();
        const startYear = Math.floor(selectedYear / 20) * 20 - 4;

        let html = `<div class="dp-header">
            <span class="dp-title">${startYear} – ${startYear + 23}</span>
            <div class="dp-nav">
                <button class="dp-nav-btn" data-action="prev-decade">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="15 18 9 12 15 6"/></svg>
                </button>
                <button class="dp-nav-btn" data-action="next-decade">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="9 6 15 12 9 18"/></svg>
                </button>
            </div>
        </div>`;

        html += '<div class="dp-year-grid">';
        for (let y = startYear; y < startYear + 24; y++) {
            let cls = 'dp-year-btn';
            if (y === currentYear) cls += ' dp-year-btn--current';
            if (y === selectedYear) cls += ' dp-year-btn--selected';
            html += `<button class="${cls}" data-year="${y}">${y}</button>`;
        }
        html += '</div>';

        this.container.innerHTML = html;

        this.container.querySelectorAll('.dp-nav-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (btn.dataset.action === 'prev-decade') {
                    this.viewDate.setFullYear(this.viewDate.getFullYear() - 24);
                } else {
                    this.viewDate.setFullYear(this.viewDate.getFullYear() + 24);
                }
                this._render();
            });
        });

        this.container.querySelectorAll('.dp-year-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.viewDate.setFullYear(parseInt(btn.dataset.year));
                this.viewMode = 'months';
                this._render();
            });
        });

        // Scroll to selected year
        const selected = this.container.querySelector('.dp-year-btn--selected');
        if (selected) {
            selected.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
    }

    setDate(dateStr) {
        this.selectedDate = this._parseValue(dateStr);
        this.viewDate = new Date(this.selectedDate.getFullYear(), this.selectedDate.getMonth(), 1);
        this.hiddenInput.value = dateStr;
        this._updateDisplay();
    }
}

function initDatePickers() {
    document.querySelectorAll('[data-datepicker]').forEach(wrapper => {
        const trigger = wrapper.querySelector('.date-display');
        const hidden = wrapper.querySelector('input[type="hidden"]');
        if (trigger && hidden) {
            new GlassDatePicker(trigger, hidden);
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initDatePickers, 50);
});
