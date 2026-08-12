# Screenshots - n8n имплементација (TELFOR труд)

Сите слики се од n8n workflow "TEST - AI Agent vs Chain (intent_parser)"
(workflow ID `CwrkhftDrYNgl08c`), зачувани рачно (Windows Snipping Tool) -
Claude Code нема способност да зачувува browser screenshots директно на
диск, само да ги прегледа во разговорот, затоа сите фајлови овде се рачно
снимени од корисникот. Секој запис подолу е верификуван - секоја слика е
повторно прочитана и содржината е потврдена да одговара на описот (не само
претпоставено од претходна сесија).

Редослед подолу е по вистински хронолошки timestamp на фајлот (не по име) -
имињата не се секогаш во хронолошки редослед бидејќи некои се именувани од
Claude, некои рачно од корисникот.

---

## 01_ai_agent_setup_and_executions.jpg

**Датум:** Aug 6, 11:21

**Прикажува:** Целосен преглед на "TEST - AI Agent vs Chain (intent_parser)"
workflow во Executions таб: листа со сите 5 извршувања (лево, сите
"Succeeded", 43.587s-10.957s), canvas со Manual Trigger → AI Agent ←
Ollama Chat Model, и отворен Logs панел со Input (целосен prompt текст на
македонски, идентичен со `graph_v1.py::intent_parser_node`) и Output
(валиден JSON `{"source_subnet":"10.0.5.0/24",...}`) за execution #1 (Aug 5,
22:50:53 - најстарото и најбавно извршување, веројатно cold-start ефект).

**Корисна за:** Implementation секција - покажува целосна AI Agent + Ollama
конфигурација во n8n. Methodology секција - листата со 5 одделни рачни
извршувања е директен доказ дека тестот навистина е повторен 5 пати (не
тврдење без доказ).

---

## 02_ai_agent_output_json_clean.jpg

**Датум:** Aug 6, 11:23

**Прикажува:** Приближен преглед на execution #5 (Aug 5, 23:03:45, најново
извршување, 12.15s) со чист, лесно читлив Output панел:
`{"source_subnet":"10.0.5.0/24","dest_subnet":"10.0.10.15","dest_port":443,"protocol":"tcp","confidence":1.0}`
- валиден JSON, идентичен со сите останати 4 извршувања.

**Корисна за:** Results секција - најчистата слика за прикажување на самиот
резултат (валиден JSON output) без визуелна бучава од execution листата.

---

## 03_ai_agent_node_architecture.jpg

**Датум:** Aug 6, 11:23

**Прикажува:** Чист canvas преглед (без отворен Logs панел) на самата node
архитектура: Manual Trigger → AI Agent node (со видливи Chat Model / Memory
/ Tool sub-connection слотови) ← Ollama Chat Model како поврзан Model
sub-node.

**Корисна за:** Implementation/Methodology секција - најдобра слика за
архитектурен дијаграм на AI Agent node структурата (нема execution/output
бучава, чист приказ на node-графот).

---

## n8n.png

**Датум:** Aug 7, 01:56

**Прикажува:** Node search панелот ("What happens next?") со пребарување
"Basic LLM Chain", директно ПРЕД node-от да биде додаден на canvas-от.
Забелешка: сликата ја вклучува целата browser прозорец (таб лента, адресна
лента `localhost:5678/workflow/CwrkhftDrYNgl08c`), не само app содржината -
земена преку OS-level screenshot алатка, не cropped на самата апликација.

**Корисна за:** Methodology/Limitations секција - оваа слика е доказ дека
node search панелот работи исправно кога го отвора човек рачно во
browser-от. Claude Code наиде на повторлив bug каде истиот панел останува
заглавен на `opacity: 0` кога се отвора преку автоматизиран/synthetic
click (документирано во `results/dev_notes.md`) - оваа слика ја покажува
рачната алтернатива што го решила проблемот, корисна за да се илустрира
зошто одредени чекори во n8n изградбата бараа рачна интервенција наместо
целосна автоматизација.

---

## basic llm node.png

**Датум:** Aug 7, 01:57

**Прикажува:** Basic LLM Chain node веднаш откако е додаден на canvas-от,
ПРЕД конфигурација: "Source for Prompt (User Message)" сè уште на default
"Connected Chat Trigger Node" (не "Define below"), Prompt полето сè уште на
default `{{ $json.chatInput }}`, "No input connected", нема Model sub-node
поврзано, Output панел покажува "No output data".

**Корисна за:** Implementation секција - "before" состојба на нов n8n node
(default конфигурација), корисна во контраст со `02_ai_agent_output_json_clean.jpg`
или `05_intent_parser_guardrail_pair_success.png` кои ја покажуваат "after"
(конфигурирана и функционална) состојба - илустрира колку конфигурација е
потребна по додавање на секој node.

---

## 05_intent_parser_guardrail_pair_success.png

**Датум:** Aug 7, 16:09

**Прикажува:** Целосен pipeline canvas: Manual Trigger → AI Agent (лева
гранка) И Manual Trigger → Basic LLM Chain → HTTP Request (десна гранка,
ново). Logs панел прикажува "HTTP Request | Success in 14ms" со Output
табела: `passed` / `errors` колони (`passed: true`, `errors: []`).

**Корисна за:** Results/Implementation секција - ова е клучен архитектурен
доказ за трудот: покажува дека HTTP Request node-от во n8n успешно го
повикува истиот `guardrails/check_intent_parser.py::check()` преку
`guardrail_api.py` (споделена Python логика, не преиспишана во n8n) и
добива идентичен guardrail резултат како во LangGraph. Ова е директна
илустрација на централниот архитектурен принцип на трудот - "иста shared
guardrail логика низ различни orchestration платформи".

---

## Сумарно

**Вкупно screenshots:** 6 (3× `.jpg`, 3× `.png`), сите верификувани валидни
(проверени file signatures) и содржински точни (сите повторно прегледани
пред овој опис).

**Празнини - делови од pipeline-от БЕЗ визуелен доказ досега:**

| Чекор (Табела 1) | n8n имплементирано? | Screenshot? |
|---|---|---|
| 1. Parse intent | Да (Basic LLM Chain + AI Agent, споредени) | Да (6 слики) |
| 2. Validate syntax | Да (Basic LLM Chain1 + Ollama Chat Model2 + HTTP Request1, n=5 тестирано - Наод #19) | Не |
| 3. Query NetBox (mock) | Не сè уште | Не |
| 4. Policy check | Не сè уште | Не |
| 5. Propose rule + plans | Не сè уште | Не |
| 6. Dry-run | Не сè уште | Не |
| 7. Human approval | Не сè уште (планирано: Wait + Form trigger) | Не |
| 8. Apply rule | Не сè уште | Не |
| 9. Verify | Не сè уште | Не |
| 10. Rollback | Не сè уште | Не |

Дополнителна забелешка: `04_basic_llm_chain_comparison_success.jpg`
(споменат во претходна верзија на овој README) никогаш не е реално
зачувана - тој конкретен наод (5/5 valid JSON, Наод #17 во dev_notes.md) е
документиран само текстуално, без придружна слика. Не е критично (бројките
се веродостојно запишани), но ако сакаш целосна визуелна документација,
вреди да се додаде подоцна.

Истата ситуација важи и за чекор 2 (validator): наодот (markdown-fence bug
+ поправка + n=5 стабилност тест, Наод #18-19 во dev_notes.md) е целосно
документиран текстуално преку DOM/JS read верификација на секое
извршување, но нема придружен screenshot. Позната празнина, не е критична
- бројките и суровиот LLM output се веродостојно запишани во dev_notes.md.

**Заклучок:** сегашната визуелна документација целосно го покрива само
чекор 1 (intent_parser) - и AI Agent vs Chain споредбата, и Chain +
guardrail интеграцијата. Чекор 2 (validator) е веќе изграден и тестиран
(Наод #18-19) но сè уште без screenshot доказ. Чекори 3-10 сè уште немаат
ниту screenshot ниту имплементација во n8n workflow-то.
