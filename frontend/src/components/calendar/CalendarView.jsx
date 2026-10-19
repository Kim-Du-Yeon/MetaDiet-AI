import { useState, useEffect } from "react";
import { getCalendar, getCalendarMonth, updateMeal, deleteMeal } from "../../api/dietApi";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export default function CalendarView({onRecordsChanged}) {
  const [selectedDate, setSelectedDate] = useState(formatLocalDate(new Date()));
  const [data, setData] = useState(null);
  const [monthData, setMonthData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [monthLoading, setMonthLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshError, setRefreshError] = useState('');
  const selectedMonth = selectedDate.slice(0, 7);

  useEffect(() => {
    fetchCalendar(selectedDate);
  }, [selectedDate]);

  useEffect(() => {
    fetchCalendarMonth(selectedMonth);
  }, [selectedMonth]);

  const fetchCalendar = async (date) => {
    setLoading(true);
    try {
      const result = await getCalendar(date);
      setData(result);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  const fetchCalendarMonth = async (yearMonth) => {
    setMonthLoading(true);
    try {
      const result = await getCalendarMonth(yearMonth);
      setMonthData(result);
    } catch (e) {
      console.error(e);
    }
    setMonthLoading(false);
  };

  const moveMonth = (delta) => {
    const [year, month] = selectedMonth.split("-").map(Number);
    const next = new Date(year, month - 1 + delta, 1);
    setSelectedDate(formatLocalDate(next));
  };

  const selectToday = () => setSelectedDate(formatLocalDate(new Date()));

  const handleEditSave = async (meal) => {
    if (saving) return;
    setSaving(true); setRefreshError('');
    try {
      await updateMeal(meal.id, parseFloat(editValue));
      setEditingId(null);
      await refreshAfterChange();
    } catch (e) {
      alert("수정 실패");
    } finally { setSaving(false); }
  };

  const refreshAfterChange = async () => {
    setRefreshError('');
    await Promise.all([fetchCalendar(selectedDate),fetchCalendarMonth(selectedMonth)]);
    try { await onRecordsChanged?.(); }
    catch (error) { setRefreshError(error.message); }
  };

  const handleDelete = async (mealId) => {
    if (saving) return;
    if (!window.confirm("이 기록을 삭제하시겠습니까?")) return;
    setSaving(true); setRefreshError('');
    try {
      await deleteMeal(mealId);
      await refreshAfterChange();
    } catch (e) {
      alert("삭제 실패");
    } finally { setSaving(false); }
  };

  const MEAL_LABELS = {
    breakfast: "🌅 아침",
    lunch: "☀️ 점심",
    dinner: "🌙 저녁",
    snack: "🍎 간식"
  };

  const groupedMeals = data?.meals?.reduce((acc, meal) => {
    if (!acc[meal.meal_type]) acc[meal.meal_type] = [];
    acc[meal.meal_type].push(meal);
    return acc;
  }, {}) || {};
  const dayMap = Object.fromEntries((monthData?.days || []).map((day) => [day.date, day]));
  const [year, month] = selectedMonth.split("-").map(Number);
  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const calendarCells = [
    ...Array.from({ length: firstDay }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const monthLabel = `${year}년 ${String(month).padStart(2, "0")}월`;

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>📅 식단 캘린더</h2>
      {refreshError && <div role="alert">{refreshError}<button onClick={refreshAfterChange} disabled={saving}>섭취량 다시 확인</button></div>}

      <div style={styles.calendarCard}>
        <div style={styles.calendarHeader}>
          <button onClick={() => moveMonth(-1)} style={styles.monthBtn} title="이전 달">‹</button>
          <strong style={styles.monthTitle}>{monthLabel}</strong>
          <button onClick={() => moveMonth(1)} style={styles.monthBtn} title="다음 달">›</button>
        </div>
        <div style={styles.legendRow}>
          <span style={styles.legendItem}><span style={{ ...styles.legendDot, backgroundColor: "#ffebee", borderColor: "#ef5350" }} /> 목표 초과</span>
          <span style={styles.legendItem}><span style={{ ...styles.legendDot, backgroundColor: "#e3f2fd", borderColor: "#42a5f5" }} /> 목표 이하</span>
          <span style={styles.legendItem}><span style={{ ...styles.legendDot, backgroundColor: "white", borderColor: "#ddd" }} /> 기록 없음</span>
        </div>
        <div style={styles.weekGrid}>
          {WEEKDAYS.map((day) => <span key={day} style={styles.weekday}>{day}</span>)}
        </div>
        <div style={styles.dayGrid}>
          {calendarCells.map((day, i) => {
            if (!day) return <div key={`empty-${i}`} style={styles.emptyDay} />;
            const dateKey = `${selectedMonth}-${String(day).padStart(2, "0")}`;
            const dayInfo = dayMap[dateKey];
            const isSelected = selectedDate === dateKey;
            const statusStyle = dayInfo?.status === "over"
              ? styles.overDay
              : dayInfo?.status === "under"
                ? styles.underDay
                : {};
            return (
              <button
                key={dateKey}
                onClick={() => setSelectedDate(dateKey)}
                style={{ ...styles.dayBtn, ...statusStyle, ...(isSelected ? styles.selectedDay : {}) }}
                title={dayInfo ? `${Math.round(dayInfo.calories)} / ${Math.round(monthData?.target_calories || 0)} kcal` : "기록 없음"}
              >
                <span>{day}</span>
                {dayInfo && <small style={styles.dayCalories}>{Math.round(dayInfo.calories)}</small>}
              </button>
            );
          })}
        </div>
        <div style={styles.calendarFooter}>
          <span style={styles.targetText}>목표 {Math.round(monthData?.target_calories || 0)}kcal</span>
          <button onClick={selectToday} style={styles.todayBtn}>오늘</button>
        </div>
      </div>

      {(loading || monthLoading) && <p style={{ textAlign: "center", color: "#999" }}>로딩 중...</p>}

      {data && (
        <>
          <div style={styles.summary}>
            {["calories", "protein_g", "carbs_g", "fat_g"].map((key) => (
              <div key={key} style={styles.summaryItem}>
                <span style={styles.summaryLabel}>
                  {key === "calories" ? "칼로리" : key === "protein_g" ? "단백질" : key === "carbs_g" ? "탄수화물" : "지방"}
                </span>
                <span style={styles.summaryValue}>{Math.round(data.total?.[key] || 0)}</span>
                <span style={styles.summaryUnit}>{key === "calories" ? "kcal" : "g"}</span>
              </div>
            ))}
          </div>

          {Object.keys(groupedMeals).length === 0 ? (
            <p style={{ textAlign: "center", color: "#999", marginTop: 40 }}>
              이 날 기록된 식단이 없습니다.
            </p>
          ) : (
            Object.entries(groupedMeals).map(([mealType, meals]) => (
              <div key={mealType} style={styles.mealGroup}>
                <h3 style={styles.mealTitle}>{MEAL_LABELS[mealType] || mealType}</h3>
                {meals.map((meal) => (
                  <div key={meal.id} style={styles.mealItem}>
                    <div style={styles.mealLeft}>
                      <span style={styles.foodName}>{meal.food_name}</span>
                      {editingId === meal.id ? (
                        <div style={styles.editRow}>
                          <input
                            aria-label="수정할 분량 (g)" min="0.1" max="10000" step="any"
                            type="number"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            style={styles.editInput}
                            autoFocus
                          />
                          <span style={styles.editUnit}>g</span>
                          <button
                            disabled={saving || !Number.isFinite(Number(editValue)) || Number(editValue) <= 0 || Number(editValue) > 10000}
                            onClick={() => handleEditSave(meal)}
                            style={styles.saveBtn}
                          >저장</button>
                          <button
                            onClick={() => setEditingId(null)}
                            style={styles.cancelBtn}
                          >취소</button>
                        </div>
                      ) : (
                        <span style={styles.foodDetail}>
                          {meal.quantity_g}g · {Math.round(meal.calories)}kcal · 단백질 {Math.round(meal.protein_g)}g
                        </span>
                      )}
                    </div>
                    <div style={styles.mealActions}>
                      <button
                        disabled={saving}
                        onClick={() => {
                          setEditingId(meal.id);
                          setEditValue(meal.quantity_g);
                        }}
                        style={styles.editBtn}
                        title="수정"
                      >✏️</button>
                      <button
                        disabled={saving}
                        onClick={() => handleDelete(meal.id)}
                        style={styles.deleteBtn}
                        title="삭제"
                      >🗑️</button>
                    </div>
                  </div>
                ))}
              </div>
            ))
          )}
        </>
      )}
    </div>
  );
}

const styles = {
  container: { padding: "20px 20px 32px", maxWidth: "600px", margin: "0 auto", overflowY: "auto", minHeight: "100%" },
  title: { fontSize: "20px", fontWeight: "bold", marginBottom: "16px" },
  calendarCard: { backgroundColor: "white", borderRadius: "12px", border: "1px solid #e0e0e0", padding: "14px", marginBottom: "16px" },
  calendarHeader: { display: "grid", gridTemplateColumns: "36px 1fr 36px", alignItems: "center", marginBottom: "10px" },
  monthBtn: { width: "36px", height: "36px", border: "1px solid #ddd", borderRadius: "8px", backgroundColor: "white", cursor: "pointer", fontSize: "22px", lineHeight: 1 },
  monthTitle: { textAlign: "center", fontSize: "16px" },
  legendRow: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px", fontSize: "12px", color: "#666" },
  legendItem: { display: "inline-flex", alignItems: "center", gap: "4px" },
  legendDot: { width: "11px", height: "11px", borderRadius: "50%", border: "1px solid #ddd", display: "inline-block" },
  weekGrid: { display: "grid", gridTemplateColumns: "repeat(7, 1fr)", marginBottom: "4px" },
  weekday: { textAlign: "center", fontSize: "12px", fontWeight: "600", color: "#777", padding: "6px 0" },
  dayGrid: { display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: "6px" },
  emptyDay: { aspectRatio: "1 / 1" },
  dayBtn: { aspectRatio: "1 / 1", minWidth: 0, border: "1px solid #e0e0e0", borderRadius: "8px", backgroundColor: "white", color: "#333", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: "600", padding: "2px" },
  overDay: { backgroundColor: "#ffebee", borderColor: "#ef5350", color: "#c62828" },
  underDay: { backgroundColor: "#e3f2fd", borderColor: "#42a5f5", color: "#1565c0" },
  selectedDay: { boxShadow: "0 0 0 2px #222 inset" },
  dayCalories: { fontSize: "9px", fontWeight: "500", marginTop: "2px" },
  calendarFooter: { display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px" },
  targetText: { fontSize: "12px", color: "#777" },
  todayBtn: { border: "none", backgroundColor: "transparent", color: "#1976d2", cursor: "pointer", fontSize: "13px", fontWeight: "600" },
  summary: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginBottom: "20px" },
  summaryItem: { backgroundColor: "white", borderRadius: "12px", padding: "12px", textAlign: "center", border: "1px solid #e0e0e0", display: "flex", flexDirection: "column" },
  summaryLabel: { fontSize: "11px", color: "#999", marginBottom: "4px" },
  summaryValue: { fontSize: "22px", fontWeight: "bold", color: "#4CAF50" },
  summaryUnit: { fontSize: "11px", color: "#999" },
  mealGroup: { backgroundColor: "white", borderRadius: "12px", padding: "16px", marginBottom: "12px", border: "1px solid #e0e0e0" },
  mealTitle: { fontSize: "14px", fontWeight: "bold", marginBottom: "10px", color: "#555" },
  mealItem: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #f5f5f5" },
  mealLeft: { display: "flex", flexDirection: "column", gap: "4px", flex: 1 },
  foodName: { fontSize: "14px", fontWeight: "500" },
  foodDetail: { fontSize: "12px", color: "#999" },
  mealActions: { display: "flex", gap: "4px", marginLeft: "8px" },
  editBtn: { background: "none", border: "none", cursor: "pointer", fontSize: "14px", padding: "4px" },
  deleteBtn: { background: "none", border: "none", cursor: "pointer", fontSize: "14px", padding: "4px" },
  editRow: { display: "flex", alignItems: "center", gap: "6px", marginTop: "4px" },
  editInput: { width: "70px", padding: "4px 8px", borderRadius: "6px", border: "1px solid #ddd", fontSize: "14px" },
  editUnit: { fontSize: "12px", color: "#999" },
  saveBtn: { padding: "4px 10px", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "12px" },
  cancelBtn: { padding: "4px 10px", backgroundColor: "#e0e0e0", color: "#555", border: "none", borderRadius: "6px", cursor: "pointer", fontSize: "12px" },
};
