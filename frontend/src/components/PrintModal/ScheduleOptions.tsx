import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Calendar, Clock, Hand, Power, Layers, Code, ListOrdered } from 'lucide-react';
import { Checkbox, DatePicker, NumberField, TimeField, type DateKey } from '../ui';
import type { ScheduleOptionsProps, ScheduleType } from './types';
import {
  formatDateInput,
  formatTimeInput,
  parseDateInput,
  parseTimeInput,
  getTimePlaceholder,
  toDateTimeLocalValue,
  type DateFormat,
  type TimeFormat,
} from '../../utils/date';

/**
 * Schedule options component for queue items.
 * Includes schedule type (ASAP/Queue/Schedule), datetime picker,
 * and options for require previous success and auto power off.
 */
export function ScheduleOptionsPanel({
  options,
  onChange,
  dateFormat = 'system',
  timeFormat = 'system',
  canControlPrinter = true,
  showStagger = false,
  printerCount = 0,
  hasGcodeSnippets = false,
}: ScheduleOptionsProps) {
  const { t, i18n } = useTranslation();
  const [dateValue, setDateValue] = useState('');
  const [timeValue, setTimeValue] = useState('');
  const [isDateValid, setIsDateValid] = useState(true);
  const [isTimeValid, setIsTimeValid] = useState(true);
  const isInitializedRef = useRef(false);

  // Initialize or sync from options.scheduledTime
  useEffect(() => {
    if (options.scheduleType !== 'scheduled') {
      isInitializedRef.current = false;
      return;
    }

    // Initialize with default time (now + 1 hour) or from existing value
    if (!isInitializedRef.current) {
      isInitializedRef.current = true;
      let date: Date;

      if (options.scheduledTime) {
        date = new Date(options.scheduledTime);
        if (isNaN(date.getTime())) {
          date = new Date();
          date.setHours(date.getHours() + 1, 0, 0, 0);
        }
      } else {
        date = new Date();
        date.setHours(date.getHours() + 1, 0, 0, 0);
        // Set initial value
        onChange({ ...options, scheduledTime: toDateTimeLocalValue(date) });
      }

      setDateValue(formatDateInput(date, dateFormat as DateFormat));
      setTimeValue(formatTimeInput(date, timeFormat as TimeFormat));
      setIsDateValid(true);
      setIsTimeValid(true);
    }
  }, [options.scheduleType, options.scheduledTime, dateFormat, timeFormat, onChange, options]);

  const handleScheduleTypeChange = (scheduleType: ScheduleType) => {
    onChange({
      ...options,
      scheduleType,
      requireManualStart: scheduleType === 'queue' ? options.requireManualStart : false,
    });
  };

  const updateScheduledTime = (newDateValue: string, newTimeValue: string) => {
    const parsedDate = parseDateInput(newDateValue, dateFormat as DateFormat);
    const parsedTime = parseTimeInput(newTimeValue);

    setIsDateValid(!!parsedDate);
    setIsTimeValid(!!parsedTime);

    if (parsedDate && parsedTime) {
      parsedDate.setHours(parsedTime.hours, parsedTime.minutes, 0, 0);
      const now = new Date();
      if (parsedDate > now) {
        onChange({ ...options, scheduledTime: toDateTimeLocalValue(parsedDate) });
      }
    }
  };

  const handleTimeChange = (value: string) => {
    setTimeValue(value);
    updateScheduledTime(dateValue, value);
  };

  const handleCalendarDateChange = (value: DateKey | '') => {
    if (!value) return;
    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(year, month - 1, day, 12, 0, 0, 0);
    const formatted = formatDateInput(date, dateFormat as DateFormat);
    setDateValue(formatted);
    updateScheduledTime(formatted, timeValue);
  };

  const calendarDateValue = /^\d{4}-\d{2}-\d{2}/.test(options.scheduledTime)
    ? (options.scheduledTime.slice(0, 10) as DateKey)
    : '';

  return (
    <div className="space-y-4">
      {/* Schedule type */}
      <div>
        <label className="block text-sm text-bambu-gray mb-2">{t('printModal.whenToPrint')}</label>
        <div className="flex gap-2">
          <button
            type="button"
            className={`flex-1 px-2 py-2 rounded-lg border text-sm flex items-center justify-center gap-1.5 transition-colors ${
              options.scheduleType === 'asap'
                ? 'bg-bambu-green border-bambu-green text-white'
                : 'bg-bambu-dark border-bambu-dark-tertiary text-bambu-gray hover:text-white'
            }`}
            onClick={() => handleScheduleTypeChange('asap')}
          >
            <Clock className="w-4 h-4" />
            {t('printModal.asap')}
          </button>
          <button
            type="button"
            className={`flex-1 px-2 py-2 rounded-lg border text-sm flex items-center justify-center gap-1.5 transition-colors ${
              options.scheduleType === 'queue'
                ? 'bg-bambu-green border-bambu-green text-white'
                : 'bg-bambu-dark border-bambu-dark-tertiary text-bambu-gray hover:text-white'
            }`}
            onClick={() => handleScheduleTypeChange('queue')}
          >
            <ListOrdered className="w-4 h-4" />
            {t('printModal.queue')}
          </button>
          <button
            type="button"
            className={`flex-1 px-2 py-2 rounded-lg border text-sm flex items-center justify-center gap-1.5 transition-colors ${
              options.scheduleType === 'scheduled'
                ? 'bg-bambu-green border-bambu-green text-white'
                : 'bg-bambu-dark border-bambu-dark-tertiary text-bambu-gray hover:text-white'
            }`}
            onClick={() => handleScheduleTypeChange('scheduled')}
          >
            <Calendar className="w-4 h-4" />
            {t('printModal.schedule')}
          </button>
        </div>
      </div>

      {/* Scheduled time input */}
      {options.scheduleType === 'scheduled' && (
        <div>
          <label className="block text-sm text-bambu-gray mb-1">{t('printModal.dateTime')}</label>
          <div className="flex gap-2">
            {/* Date input */}
            <div className="flex-1">
              <DatePicker
                ariaLabel={t('printModal.openCalendar')}
                locale={i18n.resolvedLanguage ?? i18n.language}
                value={calendarDateValue}
                onValueChange={handleCalendarDateChange}
              />
            </div>
            {/* Time input */}
            <div className="w-32">
              <TimeField
                aria-label={t('common.time', 'Time')}
                className={`w-full px-3 py-2 bg-bambu-dark border rounded-lg text-white focus:outline-none ${
                  isTimeValid
                    ? 'border-bambu-dark-tertiary focus:border-bambu-green'
                    : 'border-red-500'
                }`}
                value={timeValue}
                onChange={(e) => handleTimeChange(e.target.value)}
                placeholder={getTimePlaceholder(timeFormat as TimeFormat)}
              />
            </div>
          </div>
          {(!isDateValid || !isTimeValid) && (
            <p className="mt-1 text-xs text-red-700 dark:text-red-400">
              {t('printModal.invalidDateTime')}
            </p>
          )}
        </div>
      )}

      {/* Manual start */}
      {options.scheduleType === 'queue' && (
        <div className="flex items-center gap-2">
          <Checkbox
            id="requireManualStart"
            checked={options.requireManualStart}
            onChange={(e) => onChange({ ...options, requireManualStart: e.target.checked })}
          />
          <label htmlFor="requireManualStart" className="text-sm flex items-center gap-1 text-bambu-gray">
            <Hand className="w-3.5 h-3.5" />
            {t('printModal.requireManualStart')}
          </label>
        </div>
      )}

      {/* Require previous success */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="requirePrevious"
          checked={options.requirePreviousSuccess}
          onChange={(e) => onChange({ ...options, requirePreviousSuccess: e.target.checked })}
        />
        <label htmlFor="requirePrevious" className="text-sm text-bambu-gray">
          {t('printModal.requirePreviousSuccess')}
        </label>
      </div>

      {/* Auto power off */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="autoOffAfter"
          checked={options.autoOffAfter}
          onChange={(e) => onChange({ ...options, autoOffAfter: e.target.checked })}
          disabled={!canControlPrinter}
        />
        <label htmlFor="autoOffAfter" className={`text-sm flex items-center gap-1 ${canControlPrinter ? 'text-bambu-gray' : 'text-bambu-gray/50'}`}>
          <Power className="w-3.5 h-3.5" />
          {t('printModal.autoOffAfter')}
        </label>
      </div>

      {/* G-code injection */}
      {hasGcodeSnippets && (
        <div className="flex items-center gap-2">
          <Checkbox
            id="gcodeInjection"
            checked={options.gcodeInjection}
            onChange={(e) => onChange({ ...options, gcodeInjection: e.target.checked })}
          />
          <label htmlFor="gcodeInjection" className="text-sm flex items-center gap-1 text-bambu-gray">
            <Code className="w-3.5 h-3.5" />
            {t('printModal.gcodeInjection', 'Inject auto-print G-code')}
          </label>
        </div>
      )}

      {/* Stagger start */}
      {showStagger && options.scheduleType !== 'queue' && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="staggerEnabled"
              checked={options.staggerEnabled}
              onChange={(e) => onChange({ ...options, staggerEnabled: e.target.checked })}
            />
            <label htmlFor="staggerEnabled" className="text-sm flex items-center gap-1 text-bambu-gray">
              <Layers className="w-3.5 h-3.5" />
              {t('printModal.staggerPrinterStarts', 'Stagger printer starts')}
            </label>
          </div>

          {options.staggerEnabled && (
            <div className="ml-6 space-y-3">
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-xs text-bambu-gray mb-1">{t('printModal.staggerGroupSize', 'Group size')}</label>
                  <NumberField
                    min={1}
                    max={printerCount}
                    value={options.staggerGroupSize}
                    onChange={(e) => onChange({ ...options, staggerGroupSize: Math.max(1, parseInt(e.target.value) || 1) })}
                    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs text-bambu-gray mb-1">{t('printModal.staggerInterval', 'Interval (min)')}</label>
                  <NumberField
                    min={1}
                    max={60}
                    value={options.staggerIntervalMinutes}
                    onChange={(e) => onChange({ ...options, staggerIntervalMinutes: Math.max(1, parseInt(e.target.value) || 1) })}
                    className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green"
                  />
                </div>
              </div>
              {printerCount > 0 && (() => {
                const groupCount = Math.ceil(printerCount / options.staggerGroupSize);
                const lastGroupSize = printerCount % options.staggerGroupSize;
                const totalMinutes = (groupCount - 1) * options.staggerIntervalMinutes;
                return (
                  <p className="text-xs text-bambu-gray">
                    {t('printModal.staggerPreview', '{{printers}} printers → {{groups}} groups of {{size}}, starting every {{interval}} min', {
                      printers: printerCount,
                      groups: groupCount,
                      size: options.staggerGroupSize,
                      interval: options.staggerIntervalMinutes,
                    })}
                    {lastGroupSize !== 0 && options.staggerGroupSize < printerCount
                      ? ` (${t('printModal.staggerLastGroup', 'last group: {{count}}', { count: lastGroupSize })})`
                      : ''}
                    {groupCount > 1
                      ? ` (${t('printModal.staggerTotal', 'total: {{minutes}} min', { minutes: totalMinutes })})`
                      : ''}
                  </p>
                );
              })()}
            </div>
          )}
        </div>
      )}

      {/* Help text */}
      <p className="text-xs text-bambu-gray">
        {options.scheduleType === 'asap'
          ? t('printModal.helpAsap')
          : options.scheduleType === 'scheduled'
          ? t('printModal.helpSchedule')
          : t('printModal.helpQueue')}
      </p>
    </div>
  );
}
