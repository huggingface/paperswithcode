export interface PaperDateRangeValue {
  startDate?: string;
  endDate?: string;
}

export const paperDatePresetRange = (
  preset: "week" | "month",
  currentDate: Date,
): Required<PaperDateRangeValue> => {
  const today = new Date(currentDate);
  const start = new Date(today);
  start.setUTCDate(today.getUTCDate() - (preset === "week" ? 6 : 29));
  return {
    startDate: start.toISOString().slice(0, 10),
    endDate: today.toISOString().slice(0, 10),
  };
};

export const readPaperDateRange = (params: URLSearchParams): PaperDateRangeValue => ({
  startDate: params.get("start_date") || undefined,
  endDate: params.get("end_date") || undefined,
});

export const readHomepagePaperDateRange = (
  params: URLSearchParams,
  currentDate = new Date(),
): PaperDateRangeValue => {
  const explicitRange = readPaperDateRange(params);
  if (explicitRange.startDate || explicitRange.endDate || params.get("time") === "all_time") {
    return explicitRange;
  }

  const today = new Date(Date.UTC(
    currentDate.getUTCFullYear(),
    currentDate.getUTCMonth(),
    currentDate.getUTCDate(),
  ));
  return paperDatePresetRange("week", today);
};

export const withPaperDateRange = (
  current: URLSearchParams,
  value: PaperDateRangeValue,
) => {
  const next = new URLSearchParams(current);
  if (value.startDate) next.set("start_date", value.startDate);
  else next.delete("start_date");
  if (value.endDate) next.set("end_date", value.endDate);
  else next.delete("end_date");
  next.delete("time");
  return next;
};

export const withHomepagePaperDateRange = (
  current: URLSearchParams,
  value: PaperDateRangeValue,
) => {
  const next = withPaperDateRange(current, value);
  if (!value.startDate && !value.endDate) next.set("time", "all_time");
  return next;
};
