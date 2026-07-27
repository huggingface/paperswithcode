import { apiClient } from "@/lib/api";

export type { TrendPoint, TrendsResponse } from "@/lib/api";

export const formatTrendMonth = (month: string): string => {
  const match = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(month);
  if (!match) return month;

  const [, year, monthNumber] = match;
  const names = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `${names[Number(monthNumber) - 1]} '${year.slice(2)}`;
};

export const fetchTrends = () => apiClient.getResearchTrends();
