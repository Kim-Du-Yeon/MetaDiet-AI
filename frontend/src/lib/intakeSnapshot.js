export function validIntakeSnapshot(snapshot) {
  return snapshot?.protocol === 1 && /^[a-f0-9]{64}$/.test(snapshot.version || '')
    && Number.isFinite(snapshot.today_calories) && Number.isFinite(snapshot.target_calories)
    && snapshot.calendar?.date && Array.isArray(snapshot.calendar.meals)
    && snapshot.calendar_month?.year_month && Array.isArray(snapshot.calendar_month.days);
}
