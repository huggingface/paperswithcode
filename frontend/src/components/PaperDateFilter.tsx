import React, { useEffect, useMemo, useState } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  paperDatePresetRange,
  type PaperDateRangeValue,
} from "@/lib/paperDateRange";

export type { PaperDateRangeValue } from "@/lib/paperDateRange";

interface CalendarDay {
  iso: string;
  day: number;
  outsideMonth: boolean;
}

const MONTH_FORMATTER = new Intl.DateTimeFormat("en", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const SHORT_MONTH_FORMATTER = new Intl.DateTimeFormat("en", {
  month: "short",
  timeZone: "UTC",
});
const SINGLE_CALENDAR_QUERY = "(max-width: 640px)";

const useSingleCalendar = () => {
  const [singleCalendar, setSingleCalendar] = useState(
    () => typeof window !== "undefined" && window.matchMedia(SINGLE_CALENDAR_QUERY).matches,
  );

  useEffect(() => {
    const query = window.matchMedia(SINGLE_CALENDAR_QUERY);
    const update = (event: MediaQueryListEvent) => setSingleCalendar(event.matches);
    setSingleCalendar(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return singleCalendar;
};

const isoDate = (value: Date) => value.toISOString().slice(0, 10);
const utcDate = (value: string) => new Date(`${value}T00:00:00Z`);
const utcToday = () => {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
};
const addMonths = (value: Date, amount: number) =>
  new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + amount, 1));
const monthStart = (value: Date) =>
  new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1));
const setYear = (value: Date, year: number) =>
  new Date(Date.UTC(year, value.getUTCMonth(), 1));

const sameRange = (
  value: PaperDateRangeValue,
  expected: PaperDateRangeValue,
) => value.startDate === expected.startDate && value.endDate === expected.endDate;

const formatRange = (startDate: string, endDate: string) => {
  const start = utcDate(startDate);
  const end = utcDate(endDate);
  const startMonth = SHORT_MONTH_FORMATTER.format(start);
  const endMonth = SHORT_MONTH_FORMATTER.format(end);
  const startDay = start.getUTCDate();
  const endDay = end.getUTCDate();
  const startYear = start.getUTCFullYear();
  const endYear = end.getUTCFullYear();

  if (startDate === endDate) {
    return `${startMonth} ${startDay}, ${startYear}`;
  }
  if (startYear === endYear && start.getUTCMonth() === end.getUTCMonth()) {
    return `${startMonth} ${startDay}–${endDay}, ${startYear}`;
  }
  if (startYear === endYear) {
    return `${startMonth} ${startDay}–${endMonth} ${endDay}, ${startYear}`;
  }
  return `${startMonth} ${startDay}, ${startYear}–${endMonth} ${endDay}, ${endYear}`;
};

const calendarDays = (month: Date): CalendarDay[] => {
  const year = month.getUTCFullYear();
  const monthIndex = month.getUTCMonth();
  const first = new Date(Date.UTC(year, monthIndex, 1));
  const mondayOffset = (first.getUTCDay() + 6) % 7;
  const gridStart = new Date(first);
  gridStart.setUTCDate(first.getUTCDate() - mondayOffset);

  return Array.from({ length: 42 }, (_, index) => {
    const value = new Date(gridStart);
    value.setUTCDate(gridStart.getUTCDate() + index);
    return {
      iso: isoDate(value),
      day: value.getUTCDate(),
      outsideMonth: value.getUTCMonth() !== monthIndex,
    };
  });
};

const MonthCalendar: React.FC<{
  month: Date;
  today: string;
  startDate?: string;
  endDate?: string;
  onSelect: (date: string) => void;
  yearLabel: string;
  yearValue: string;
  onYearChange: (value: string) => void;
  secondary?: boolean;
}> = ({
  month,
  today,
  startDate,
  endDate,
  onSelect,
  yearLabel,
  yearValue,
  onYearChange,
  secondary = false,
}) => {
  const days = useMemo(() => calendarDays(month), [month]);
  return (
    <section className={`paper-date-calendar${secondary ? " paper-date-calendar-secondary" : ""}`}>
      <label className="paper-date-year">
        <span>{yearLabel}</span>
        <input
          type="number"
          inputMode="numeric"
          min="1900"
          max={today.slice(0, 4)}
          step="1"
          value={yearValue}
          onChange={(event) => onYearChange(event.target.value)}
        />
      </label>
      <h3>{MONTH_FORMATTER.format(month)}</h3>
      <div className="paper-date-weekdays" aria-hidden="true">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => <span key={day}>{day}</span>)}
      </div>
      <div className="paper-date-days">
        {days.map((date) => {
          const selected = date.iso === startDate || date.iso === endDate;
          const inRange = Boolean(startDate && endDate && date.iso > startDate && date.iso < endDate);
          const disabled = date.outsideMonth || date.iso > today;
          return (
            <button
              type="button"
              key={date.iso}
              aria-label={date.iso}
              aria-selected={selected}
              disabled={disabled}
              className={[
                "paper-date-day",
                date.outsideMonth ? "outside" : "",
                selected ? "selected" : "",
                inRange ? "in-range" : "",
                date.iso === today ? "today" : "",
              ].filter(Boolean).join(" ")}
              onClick={() => onSelect(date.iso)}
            >
              {date.day}
            </button>
          );
        })}
      </div>
    </section>
  );
};

const MonthNavigation: React.FC<{
  calendar: "start" | "end";
  onPrevious: () => void;
  onNext: () => void;
  secondary?: boolean;
}> = ({ calendar, onPrevious, onNext, secondary = false }) => (
  <div
    className={`paper-date-navigation-group${secondary ? " paper-date-navigation-group-secondary" : ""}`}
  >
    <button type="button" aria-label={`Previous ${calendar} month`} onClick={onPrevious}>
      ←
    </button>
    <button type="button" aria-label={`Next ${calendar} month`} onClick={onNext}>
      →
    </button>
  </div>
);

export const PaperDateFilter: React.FC<PaperDateRangeValue & {
  onChange: (value: PaperDateRangeValue) => void;
  currentDate?: string;
}> = ({ startDate, endDate, onChange, currentDate }) => {
  const singleCalendar = useSingleCalendar();
  const currentDay = currentDate ? utcDate(currentDate) : utcToday();
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState<string>();
  const [draftEnd, setDraftEnd] = useState<string>();
  const [startVisibleMonth, setStartVisibleMonth] = useState(() => monthStart(currentDay));
  const [endVisibleMonth, setEndVisibleMonth] = useState(() => addMonths(monthStart(currentDay), 1));
  const [startYear, setStartYear] = useState(() => String(currentDay.getUTCFullYear()));
  const [endYear, setEndYear] = useState(() => String(currentDay.getUTCFullYear()));
  const current = { startDate, endDate };
  const week = paperDatePresetRange("week", currentDay);
  const month = paperDatePresetRange("month", currentDay);
  const today = isoDate(currentDay);
  const custom = Boolean(startDate && endDate && !sameRange(current, week) && !sameRange(current, month));

  const openRange = () => {
    setDraftStart(startDate);
    setDraftEnd(endDate);
    const nextStartMonth = monthStart(startDate ? utcDate(startDate) : currentDay);
    const nextEndMonth = monthStart(endDate ? utcDate(endDate) : addMonths(nextStartMonth, 1));
    setStartVisibleMonth(nextStartMonth);
    setEndVisibleMonth(nextEndMonth);
    setStartYear(String(nextStartMonth.getUTCFullYear()));
    setEndYear(String(nextEndMonth.getUTCFullYear()));
    setOpen(true);
  };

  const changeYear = (
    value: string,
    setInputYear: (value: string) => void,
    setMonth: React.Dispatch<React.SetStateAction<Date>>,
  ) => {
    setInputYear(value);
    if (!/^\d{4}$/.test(value)) return;

    const year = Number(value);
    if (year >= 1900 && year <= currentDay.getUTCFullYear()) {
      setMonth((visibleMonth) => setYear(visibleMonth, year));
    }
  };

  const navigateMonth = (
    visibleMonth: Date,
    amount: number,
    setMonth: React.Dispatch<React.SetStateAction<Date>>,
    setInputYear: (value: string) => void,
  ) => {
    const nextMonth = addMonths(visibleMonth, amount);
    setMonth(nextMonth);
    setInputYear(String(nextMonth.getUTCFullYear()));
  };

  const selectDate = (value: string) => {
    if (!draftStart || draftEnd) {
      setDraftStart(value);
      setDraftEnd(undefined);
    } else if (value < draftStart) {
      setDraftStart(value);
    } else {
      setDraftEnd(value);
    }
  };

  const clear = () => {
    onChange({});
    setOpen(false);
  };

  return (
    <div
      className={`paper-date-filter${singleCalendar ? " paper-date-filter-single-calendar" : ""}`}
      role="group"
      aria-label="Publication date"
    >
      <button
        type="button"
        className={`sort-btn sort-btn-time${sameRange(current, week) ? " active" : ""}`}
        onClick={() => onChange(week)}
      >
        Last Week
      </button>
      <button
        type="button"
        className={`sort-btn sort-btn-time${sameRange(current, month) ? " active" : ""}`}
        onClick={() => onChange(month)}
      >
        Last Month
      </button>
      <button
        type="button"
        className={`sort-btn sort-btn-time${!startDate && !endDate ? " active" : ""}`}
        onClick={() => onChange({})}
      >
        All Time
      </button>
      <Popover
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen) openRange();
          else setOpen(false);
        }}
      >
        <PopoverTrigger asChild>
          <button
            type="button"
            className={`sort-btn sort-btn-time${custom ? " active" : ""}`}
            aria-label={custom ? "Change date range" : "Select a range"}
          >
            {custom && startDate && endDate ? formatRange(startDate, endDate) : "Select a range"}
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="end"
          className={`paper-date-popover${singleCalendar ? " paper-date-popover-single-calendar" : ""}`}
          role="dialog"
          aria-label="Select a date range"
        >
          <div className="paper-date-popover-header">
            <h2>Select a date range</h2>
            <p>Choose an inclusive start and end publication date.</p>
          </div>
          <div className="paper-date-navigation">
            <MonthNavigation
              calendar="start"
              onPrevious={() =>
                navigateMonth(
                  startVisibleMonth,
                  -1,
                  setStartVisibleMonth,
                  setStartYear,
                )
              }
              onNext={() =>
                navigateMonth(
                  startVisibleMonth,
                  1,
                  setStartVisibleMonth,
                  setStartYear,
                )
              }
            />
            {!singleCalendar && (
              <MonthNavigation
                calendar="end"
                onPrevious={() =>
                  navigateMonth(
                    endVisibleMonth,
                    -1,
                    setEndVisibleMonth,
                    setEndYear,
                  )
                }
                onNext={() =>
                  navigateMonth(
                    endVisibleMonth,
                    1,
                    setEndVisibleMonth,
                    setEndYear,
                  )
                }
                secondary
              />
            )}
          </div>
          <div className="paper-date-calendars">
            <MonthCalendar
              month={startVisibleMonth}
              today={today}
              startDate={draftStart}
              endDate={draftEnd}
              onSelect={selectDate}
              yearLabel={singleCalendar ? "Year" : "Start year"}
              yearValue={startYear}
              onYearChange={(value) => changeYear(value, setStartYear, setStartVisibleMonth)}
            />
            {!singleCalendar && (
              <MonthCalendar
                month={endVisibleMonth}
                today={today}
                startDate={draftStart}
                endDate={draftEnd}
                onSelect={selectDate}
                yearLabel="End year"
                yearValue={endYear}
                onYearChange={(value) => changeYear(value, setEndYear, setEndVisibleMonth)}
                secondary
              />
            )}
          </div>
          <div className="paper-date-actions">
            <button type="button" className="paper-date-clear" onClick={clear}>Clear range</button>
            <div>
              <button type="button" onClick={() => setOpen(false)}>Cancel</button>
              <button
                type="button"
                className="paper-date-apply"
                disabled={!draftStart || !draftEnd}
                onClick={() => {
                  if (draftStart && draftEnd) onChange({ startDate: draftStart, endDate: draftEnd });
                  setOpen(false);
                }}
              >
                Apply
              </button>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};
