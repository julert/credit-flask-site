# app.py
from flask import Flask, render_template_string, request, jsonify
import math

app = Flask(__name__)

# ----------------- константы -----------------
MIN_AGE = 18
MAX_AGE = 70
MIN_WORK_MONTHS = 3
LIVING_WAGE = 15_000          # прожиточный минимум (руб.)
BASE_RATE_MONTH = 0.015       # 1,5 % в месяц
MAX_PAYMENT_SHARE = 0.45      # доля платежа в совокупном доходе семьи
# --------------------------------------------

FORM_TEMPLATE = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Онлайн-заявка на кредит</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container py-5">
  <h2 class="mb-4">Заявка на потребительский кредит</h2>
  <form id="creditForm" class="row g-3 needs-validation" novalidate>
    <!-- 1. Возраст -->
    <div class="col-md-4">
      <label class="form-label">Возраст (полных лет)</label>
      <input type="number" min="0" max="120" class="form-control" name="age" required>
    </div>

    <!-- 2. Тип занятости -->
    <div class="col-md-4">
      <label class="form-label">Тип занятости</label>
      <select class="form-select" name="employment" required>
        <option value="" selected disabled>Выберите...</option>
        <option value="наёмный">Наёмный работник</option>
        <option value="самозанятый">Самозанятый</option>
        <option value="студент">Студент</option>
        <option value="пенсионер">Пенсионер</option>
        <option value="безработный">Безработный</option>
      </select>
    </div>

    <!-- 3. Срок постоянной работы -->
    <div class="col-md-4">
      <label class="form-label">Срок постоянной работы</label>
      <select class="form-select" name="work_duration" required>
        <option value="" selected disabled>Выберите...</option>
        <option value="более 3">Более 3 месяцев</option>
        <option value="менее 3">Менее 3 месяцев</option>
        <option value="безработный">Безработный</option>
      </select>
    </div>

    <!-- 4. Доход клиента -->
    <div class="col-md-4">
      <label class="form-label">Ваш ежемесячный доход (₽)</label>
      <input type="number" min="0" class="form-control" name="income" required>
    </div>

    <!-- 5. Семейное положение -->
    <div class="col-md-4">
      <label class="form-label">Семейное положение</label>
      <select class="form-select" name="marital" required>
        <option value="" selected disabled>Выберите...</option>
        <option value="женат/замужем">Женат / замужем</option>
        <option value="холост/не замужем">Холост / не замужем</option>
      </select>
    </div>

    <!-- 6. Доход супруга(-и) -->
    <div class="col-md-4">
      <label class="form-label">Ежемесячный доход супруга(-и) (₽)<br><small class="text-muted">если нет – оставьте 0</small></label>
      <input type="number" min="0" class="form-control" name="spouse_income" value="0">
    </div>

    <!-- 7. Кол-во иждивенцев -->
    <div class="col-md-4">
      <label class="form-label">Количество иждивенцев</label>
      <input type="number" min="0" max="20" class="form-control" name="dependents" value="0">
    </div>

    <!-- 8. Кредитная история -->
    <div class="col-md-4">
      <label class="form-label">Кредитная история</label>
      <select class="form-select" name="credit_history" required>
        <option value="" selected disabled>Выберите...</option>
        <option value="есть">Есть (положительная)</option>
        <option value="плохая">Были просрочки</option>
        <option value="нет">Никогда не брал(а) кредитов</option>
      </select>
    </div>

    <!-- 9. Сумма кредита -->
    <div class="col-md-4">
      <label class="form-label">Сумма кредита (₽)</label>
      <input type="number" min="1000" class="form-control" name="amount" required>
    </div>

    <!-- 10. Срок кредита -->
    <div class="col-md-4">
      <label class="form-label">Срок (мес.)</label>
      <input type="number" min="1" max="360" class="form-control" name="term" required>
    </div>

    <div class="col-12">
      <button class="btn btn-primary" type="submit">Отправить заявку</button>
    </div>
  </form>

  <!-- Блок с результатом -->
  <div id="result" class="mt-4"></div>
</div>

<script>
document.getElementById('creditForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form).entries());
  const res = await fetch('/check', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(data)
  });
  const json = await res.json();
  const box = document.getElementById('result');
  box.innerHTML = `<div class="alert alert-${json.ok?'success':'danger'}">${json.message}</div>`;
});
</script>
</body>
</html>
"""


# ----------------- бизнес-логика -----------------
def scoring(data: dict) -> dict:
    """
    Возвращает dict с ключами:
        ok: bool – одобрено или нет
        message: str – текстовое пояснение
        payment: int – ежемесячный платёж (если одобрено)
        rate: float – ставка в месяц (если одобрено)
    """
    score = 0
    notes = []

    # 1. Возраст
    age = int(data['age'])
    if age < MIN_AGE or age > MAX_AGE:
        return {"ok": False, "message": "Отказ: возраст вне диапазона 18-70 лет."}
    if age < 21:
        score -= 10
        notes.append("Молодой возраст")
    elif age > 60:
        score -= 5
        notes.append("Предпенсионный/пенсионный возраст")
    else:
        score += 5

    # 2. Тип занятости
    emp = data['employment']
    if emp == 'безработный':
        return {"ok": False, "message": "Отказ: безработным кредит не выдаётся."}
    if emp in ('студент', 'пенсионер'):
        score -= 10
        notes.append(f"Тип занятости: {emp}")
    elif emp == 'самозанятый':
        score -= 5
        notes.append("Самозанятый")
    else:
        score += 5

    # 3. Срок работы
    wd = data['work_duration']
    if wd == 'менее 3':
        score -= 10
        notes.append("Стаж < 3 мес.")
    elif wd == 'безработный':
        pass  # уже отсеяли выше
    else:
        score += 5

    # 4-6. Доходы
    income = int(data['income'])
    spouse_income = int(data.get('spouse_income') or 0)
    total_income = income + spouse_income
    if total_income < 2 * LIVING_WAGE:
        return {"ok": False, "message": "Отказ: совокупный доход семьи менее 2 прожиточных минимумов."}

    # 7. Иждивенцы
    dep = int(data.get('dependents') or 0)
    needed = dep * LIVING_WAGE
    if total_income - needed < LIVING_WAGE:
        return {"ok": False, "message": "Отказ: после учёта иждивенцев остаётся менее 1 прожиточного минимума."}
    if dep > 3:
        score -= 5
        notes.append("Многодетность")

    # 8. Кредитная история
    ch = data['credit_history']
    if ch == 'плохая':
        score -= 20
        notes.append("Плохая КИ")
    elif ch == 'нет':
        score -= 5
        notes.append("КИ отсутствует")
    else:
        score += 10

    # 9-10. Сумма и срок
    amount = int(data['amount'])
    term = int(data['term'])
    rate = BASE_RATE_MONTH
    if score < 0:
        rate += 0.005  # добавка 0,5 % если «слабый» клиент
    payment = math.ceil(amount * (rate * (1 + rate) ** term) / ((1 + rate) ** term - 1))
    if payment > MAX_PAYMENT_SHARE * total_income:
        return {"ok": False, "message": "Отказ: платёж превышает 45 % совокупного дохода семьи."}

    # Итог
    if score >= 0:
        return {
            "ok": True,
            "message": f"Кредит одобрен! Ежемесячный платёж: {payment:,} ₽, ставка: {rate*12:.1%} годовых.",
            "payment": payment,
            "rate": rate
        }
    else:
        return {"ok": False, "message": "Отказ по совокупности факторов: " + "; ".join(notes)}


# ----------------- маршруты Flask -----------------
@app.route('/')
def index():
    return render_template_string(FORM_TEMPLATE)


@app.route('/check', methods=['POST'])
def check():
    return jsonify(scoring(request.json))


# ----------------- запуск -----------------
if __name__ == '__main__':
    app.run(debug=True)
    # app.py (конец файла)
if __name__ == '__main__':
    app.run(debug=True)   # локально
# при запуске gunicorn эта часть игнорируется