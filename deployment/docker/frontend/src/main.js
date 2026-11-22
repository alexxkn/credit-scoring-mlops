const EXAMPLE = {
  LIMIT_BAL: 50000, SEX: 2, EDUCATION: 2, MARRIAGE: 1, AGE: 30,
  PAY_0: 2, PAY_2: 2, PAY_3: 0, PAY_4: 0, PAY_5: 0, PAY_6: 0,
  BILL_AMT1: 48000, BILL_AMT2: 47000, BILL_AMT3: 46000, BILL_AMT4: 45000, BILL_AMT5: 44000, BILL_AMT6: 43000,
  PAY_AMT1: 0, PAY_AMT2: 1500, PAY_AMT3: 1500, PAY_AMT4: 1500, PAY_AMT5: 1500, PAY_AMT6: 1500,
};

const form = document.getElementById("client-form");
for (const [name, value] of Object.entries(EXAMPLE)) {
  const label = document.createElement("label");
  label.textContent = name;
  const input = document.createElement("input");
  input.name = name;
  input.type = "number";
  input.step = "any";
  input.value = value;
  label.appendChild(input);
  form.appendChild(label);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = Object.fromEntries([...new FormData(form)].map(([name, value]) => [name, Number(value)]));
  const error = document.getElementById("error");
  error.hidden = true;
  const response = await fetch("api/predict", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) {
    error.textContent = `Ошибка ${response.status}: ${JSON.stringify(data.detail)}`;
    error.hidden = false;
    return;
  }
  document.getElementById("probability").textContent = `${(data.default_probability * 100).toFixed(1)}%`;
  document.getElementById("decision").textContent = data.default_prediction ? "высокий риск дефолта" : "низкий риск";
  document.getElementById("version").textContent = data.model_version;
  document.getElementById("request-id").textContent = data.request_id;
  document.getElementById("result").hidden = false;
});
