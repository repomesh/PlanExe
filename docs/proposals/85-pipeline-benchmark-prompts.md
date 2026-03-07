# Proposal 85: Pipeline Benchmark Prompt Suite (10 Prompts)

**Author:** EgonBot  
**Date:** 2026-03-07  
**Status:** Proposal  
**Purpose:** Establish a standard test suite for identifying weak points in the PlanExe pipeline across diverse domains, prompt structures, and failure modes.

---

## 1. Why a Benchmark Suite

A single run reveals one failure. Ten diverse runs reveal a pattern.

Each prompt in this suite is designed to stress-test a specific pipeline characteristic — not just "does it complete?" but "where does it break, and what does the output look like when it does?"

The suite is intended to be run against any model or profile change and the results compared. Combined with the drift evaluation framework (Proposal 84), each run produces both a completion status and a fidelity score.

---

## 2. Design Principles

Each prompt in the suite:
- Is 300–800 words (per prompt writing guide)
- Includes explicit scope, constraints, and success criteria
- Covers a different domain and failure-mode risk profile
- Is tagged with which pipeline stages it stresses most
- Is tagged with which drift types it's most likely to reveal

The 10 prompts span:
- 5 primary domains: infrastructure, social enterprise, tech product, operations, governance
- 3 prompt structures: hard constraint heavy, uncertainty heavy, scope-boundary heavy
- 2 adversarial prompts: designed to tempt specific drift patterns in the model

---

## 3. The 10 Prompts

---

### Prompt 01 — Community Vegetable Garden (Simple Baseline)

**Domain:** Community / social  
**Stress:** Baseline — all stages, low schema complexity  
**Drift risk:** Scope expansion (small project → neighbourhood movement), confidence inflation  
**Tag:** `baseline`

```
Goal:
Plan the setup of a shared vegetable garden for a residential apartment complex in Copenhagen, Denmark.

Context:
The apartment complex has 48 units. There is an unused courtyard of approximately 200 square metres. Residents have expressed interest informally but there is no formal committee or funding yet. The garden is intended for food production and community connection, not commercial sale.

Target users:
Residents of the complex. Decision authority rests with the homeowners association (ejerforening).

Scope (in):
- Bed design and layout for the courtyard space
- Water access and basic irrigation
- Tool storage
- Governance (who maintains, rules for participation)
- Estimated startup costs
- Timeline from proposal to first harvest

Scope (out):
- Composting infrastructure (defer to phase 2)
- Beekeeping or chickens (explicitly excluded — not permitted under current bylaws)
- Any commercial activity or external users
- Grant applications (not available for this type of project)

Constraints:
- Budget: DKK 20,000–40,000 total startup (resident-funded)
- Timeline: operational within one growing season (April–June start)
- Must be reversible — courtyard must be restorable to paved surface if residents vote to end it

Success criteria:
- At least 30 of 48 households participate in the first season
- Self-sustaining governance by end of season 1 (no paid coordinator)
- No unresolved disputes about plot allocation

Resources:
- Volunteer labour from residents
- No dedicated staff
- Potential partnership with local garden centre for materials discount
```

---

### Prompt 02 — Rural Telemedicine Clinic (Regulatory Heavy)

**Domain:** Healthcare / infrastructure  
**Stress:** `PreProjectAssessmentTask`, `ExpertDetails`, `ReviewPlanTask`  
**Drift risk:** Regulatory posture drift (uncertain approvals treated as settled), unsupported clinical claims  
**Tag:** `regulatory`

```
Goal:
Establish a telemedicine clinic serving three remote villages in northern Norway — Kautokeino, Karasjok, and Tana — with a combined population of approximately 3,200 people. The clinic will provide video consultations with GPs and specialists, prescription fulfilment via pharmacy delivery, and basic vital-sign monitoring via home devices distributed to patients with chronic conditions.

Context:
The region has a single GP for every 800+ residents. Specialist wait times exceed 6 months for non-urgent referrals. Sami-language services are legally required under Norwegian law for a significant portion of the patient population. Internet infrastructure is limited — satellite broadband is the primary connectivity option for most households.

Target users:
Patients in the three municipalities. Secondary users: GPs and specialists connecting remotely.

Scope (in):
- Telemedicine platform selection and procurement
- Device distribution programme for chronic-condition patients
- Sami-language service design
- Integration with existing Norwegian health record system (Helsenorge/DIPS)
- Staffing model for a part-time local health coordinator in each village
- Regulatory approvals required under Norwegian Health Direktorat rules

Scope (out):
- Physical clinic construction (explicitly excluded — virtual-first only)
- Emergency services or ambulance coordination (separate programme)
- Mental health specialisation (defer to phase 2 pending separate funding)
- Cross-border services to Finland or Sweden

Constraints:
- Budget: NOK 8M–12M for 3-year pilot
- Timeline: first consultations operational within 18 months
- Regulatory: must comply with Norm for informasjonssikkerhet og personvern i helse- og omsorgssektoren
- Language: Sami-language interface is a hard requirement, not optional

Uncertainties:
- Regulatory approval timeline is unknown — plan must treat this as a risk, not a certainty
- Satellite bandwidth may not support high-resolution video in all conditions
- Patient adoption rate is unknown

Success criteria:
- 500+ consultations in year 1
- Wait time for GP consultation under 5 days
- Patient satisfaction score above 3.8/5.0
- Zero data protection incidents
```

---

### Prompt 03 — Urban Cycling Infrastructure (Multi-Stakeholder)

**Domain:** Urban planning / infrastructure  
**Stress:** `SelectScenarioTask` (multiple viable scenarios), `DistillAssumptionsTask`  
**Drift risk:** Scope expansion (city-wide transformation), priority drift (optional features promoted)  
**Tag:** `multi-stakeholder`, `scenario-heavy`

```
Goal:
Design a protected cycling lane network connecting three neighbourhoods in Ghent, Belgium: Dampoort, Rabot, and Sint-Amandsberg. The network should create safe, separated cycling routes between these districts and the city centre, targeting commuters and school-run traffic as primary users.

Context:
Ghent has an existing cycling culture but infrastructure gaps between these eastern neighbourhoods create dangerous mixing of cyclists and tram/bus routes along Watersportbaan and Dendermondsestraat. The city has committed to reducing car access in the centre by 2030 but specific infrastructure investment has not been allocated to these corridors.

Target users:
Daily commuter cyclists (primary). Secondary: school-run parents, recreational cyclists.

Scope (in):
- Route planning for three corridors (Dampoort–centre, Rabot–centre, Sint-Amandsberg–centre)
- Infrastructure specification: lane width, separation type, surfacing
- Intersection redesign at four identified conflict points
- Stakeholder consultation process (residents, tram operator De Lijn, delivery companies)
- Timeline and phasing
- Budget estimate per corridor

Scope (out):
- E-bike charging infrastructure (not in scope for this plan)
- Cargo bike rental programme (separate initiative already in progress)
- Vehicular traffic rerouting design (handled by Stad Gent mobility team — reference only)
- Maintenance contracts (post-construction operational phase excluded)

Constraints:
- Budget: EUR 4M–7M across all three corridors
- Timeline: construction-ready designs within 24 months
- Political constraint: cannot remove tram tracks on any route

Success criteria:
- Cycling modal share on target corridors increases by 15% within 2 years of completion
- Zero cyclist fatalities on target corridors post-construction
- De Lijn sign-off on intersection designs

Uncertainties:
- Exact utility routing under Dendermondsestraat is unconfirmed — subsurface survey required
- Property owner easement negotiations on Rabot corridor may extend timeline
```

---

### Prompt 04 — Independent Bookshop Revival (Small Business)

**Domain:** Retail / small business  
**Stress:** `MakeAssumptionsTask`, `ExpertCriticismTask`  
**Drift risk:** Business model drift (bookshop → content platform), unsupported financial claims  
**Tag:** `small-business`, `constraint-heavy`

```
Goal:
Relaunch an independent bookshop in Bristol, UK that closed during COVID and is being reopened by the original owner's daughter. The shop has a 60 square metre ground floor retail space on Gloucester Road with an existing lease (3 years remaining, monthly rent GBP 2,800). The owner has GBP 35,000 in personal savings to invest.

Context:
Gloucester Road is one of the UK's longest independent shopping streets. The bookshop previously had a loyal local customer base focused on literary fiction and local history. The owner's daughter is a librarian by training with no prior business ownership experience. She intends to run the shop herself with one part-time assistant.

Target users:
Local residents (primary). Secondary: tourists visiting Gloucester Road, local schools for reading programme supplies.

Scope (in):
- Shop fit-out and initial stock plan
- Pricing and margin model
- Opening programme and local marketing
- Online presence (basic website + ordering, not a full e-commerce operation)
- Community events plan (author talks, book clubs)
- Financial sustainability model for years 1–3

Scope (out):
- Café or food service (explicitly excluded — lease does not permit food preparation)
- Wholesale supply to other retailers
- Franchise or expansion (this is a single-location plan only)
- Venture or investor funding (owner does not want external shareholders)

Constraints:
- Budget: GBP 35,000 total (no external capital)
- Must be profitable by month 18
- Owner works full-time in the shop — no remote management model
- Single location only

Success criteria:
- Break-even by month 12
- 300 regular customers (monthly purchasers) by end of year 1
- At least 6 community events in year 1 with average 20+ attendees

Uncertainties:
- Foot traffic recovery on Gloucester Road since COVID has been uneven — assume cautiously
- Online book market is highly competitive — do not assume e-commerce will generate significant revenue
```

---

### Prompt 05 — Municipal Composting Programme (Government Operations)

**Domain:** Government / waste management  
**Stress:** `GovernanceTask`, `WBSTask`, structured output schema compliance  
**Drift risk:** Scope expansion (city-wide transformation), confidence inflation on adoption rates  
**Tag:** `government`, `operations`

```
Goal:
Design a kerbside food-waste composting collection programme for a mid-sized Danish municipality (population 85,000) currently without food-waste separation. The programme will cover all residential households and produce compost for municipal park and road-verge maintenance.

Context:
Danish national law (Affaldsbekendtgørelsen) requires food-waste separation by 2025. The municipality has missed the deadline and is under pressure from the Danish Environmental Protection Agency (Miljøstyrelsen) to comply. An existing waste contractor handles residual waste and recycling collection — the composting programme must either extend the existing contract or run as a separate tender.

Target users:
All 38,000 residential households in the municipality. Secondary: municipal parks department as compost end-user.

Scope (in):
- Brown bin distribution to all households
- Collection route design
- Processing facility options (in-house vs. regional facility partnership)
- Resident communication and onboarding campaign
- Contamination management process
- Regulatory compliance documentation for Miljøstyrelsen
- Cost model for years 1–5

Scope (out):
- Commercial or industrial food waste (separate regulatory track)
- Garden waste (already handled by existing green bin programme)
- Biogas conversion (not feasible at this municipality's scale — do not recommend)
- Composting toilets or any residential composting programme (centralised collection only)

Constraints:
- Budget: DKK 12M–18M over 3 years (capital + operating)
- Timeline: compliant programme operational within 12 months
- Must work within existing procurement rules (EU tender threshold applies)
- Political constraint: no new municipal vehicles — must use contractor model

Success criteria:
- 85%+ household participation rate by year 2
- Food-waste contamination rate below 5% by end of year 1
- Miljøstyrelsen compliance certificate received
- Compost certified for agricultural/horticultural use under Danish standards

Uncertainties:
- Regional composting facility availability is unconfirmed — plan must present both options
- Participation rates in comparable municipalities range from 60%–92% — treat as uncertain
```

---

### Prompt 06 — AI Tutoring Tool for Secondary Schools (Tech Product)

**Domain:** EdTech / software product  
**Stress:** `SelectScenarioTask`, `ReviewPlanTask` (multi-turn, complex schema)  
**Drift risk:** Scope expansion (tutoring tool → AI education platform), customer drift (students → institutions), confidence inflation on learning outcomes  
**Tag:** `tech-product`, `adversarial-scope`

```
Goal:
Build a web-based AI tutoring tool for GCSE Mathematics students aged 14–16 in England. The tool provides adaptive practice questions, step-by-step worked solutions, and tracks which topics a student is struggling with. It is sold directly to students and parents (B2C), not through schools.

Context:
The founders are two former maths teachers who tutored privately for 10 years. They have built a prototype with basic question generation and want to build a sustainable bootstrapped business. They have GBP 120,000 in savings between them.

Target users:
GCSE Maths students aged 14–16 (primary user). Parents who pay for the subscription (buyer). The tool is not sold to schools or teachers. Do not design for a classroom or institutional sales model.

Scope (in):
- Adaptive question delivery across GCSE Maths topics (AQA and Edexcel specifications)
- Step-by-step worked solution generation
- Student progress tracking dashboard (student-facing)
- Parent payment and subscription management
- Simple parent dashboard (progress summary only)
- Marketing strategy targeting students and parents

Scope (out):
- Institutional/school licensing (explicitly excluded — B2C only)
- Teacher dashboards or classroom integration
- A-Level content (phase 2 only)
- Science subjects (Maths only)
- Native mobile apps (web-only for now)
- Live tutoring or human tutor marketplace

Constraints:
- Budget: GBP 120,000 total bootstrapped (no external investment)
- Team: 2 founders, will hire 1 developer and 1 part-time content editor
- Must be profitable within 18 months
- Price point: GBP 12–18/month (market rate for this segment)

Success criteria:
- 500 paying subscribers by month 6
- 2,000 paying subscribers by month 18
- NPS score above 45
- Average 3+ sessions per week per active student

Uncertainties:
- AI generation accuracy on edge-case maths questions is unknown — assume errors will occur and plan for content moderation
- Student retention beyond 3 months is unknown
- Do not assume viral growth — treat all marketing as paid
```

---

### Prompt 07 — Emergency Flood Response Coordination (Crisis / Operations)

**Domain:** Emergency management  
**Stress:** `PremiseAttackTask`, `NegativeFeedbackTask`, time-pressure structured output  
**Drift risk:** Scope expansion (local → national response), confidence inflation on coordination outcomes  
**Tag:** `crisis`, `high-stakes`

```
Goal:
Design a 72-hour emergency coordination plan for a major flooding event in the Limfjord region of Jutland, Denmark. The plan covers the immediate response window from first alert to evacuation completion for an estimated 4,500 residents in low-lying areas around Løgstør and Farsø.

Context:
Climate modelling indicates a 1-in-50-year flood event is now expected every 8–12 years. A recent event in 2024 exposed coordination failures between Vesthimmerlands Kommune, Beredskabsstyrelsen (emergency management agency), and private utilities. This plan is commissioned by the municipality to address those gaps before the next event.

Target users:
Crisis coordinators at the municipality, Beredskabsstyrelsen liaisons, and utility operators (TREFOR, TDC). Secondary: evacuation teams and volunteers.

Scope (in):
- Alert trigger criteria and notification cascade (first 0–6 hours)
- Evacuation zone definitions and routing
- Shelter capacity and logistics (24–72 hours)
- Utility shutdown coordination (power, gas, water)
- Communication plan for residents (Danish + limited German/English for tourists)
- Inter-agency handoff protocols
- After-action review trigger

Scope (out):
- Post-flood recovery and insurance claims (separate phase)
- Infrastructure repair (not an emergency operations concern)
- Climate adaptation or flood barrier design (long-term infrastructure programme)
- National-level coordination above Beredskabsstyrelsen (they provide liaison, not direct command)

Constraints:
- This is a 72-hour operational plan only — do not plan beyond the immediate response window
- Budget for the plan document: DKK 0 (this is a policy/operational design, not a capital project)
- Resources are as-is: no new staff, no new equipment assumed
- Existing mutual aid agreements with neighbouring municipalities must be referenced

Success criteria:
- Zero preventable fatalities attributable to coordination failure
- All 4,500 residents in evacuation zones reachable within 2 hours of alert
- Utility shutdown completed before flood peak in 90% of scenarios

Uncertainties:
- Exact flood extent depends on event magnitude — plan for three scenarios (minor, major, extreme)
- Mobile network congestion during mass alert is expected — plan must not rely solely on mobile
```

---

### Prompt 08 — Electric Vehicle Fleet Conversion (Corporate Operations)

**Domain:** Corporate / fleet management  
**Stress:** `CostBreakdownTask`, `GanttTask`, financial structured output  
**Drift risk:** Confidence inflation on cost savings, unsupported charge network claims  
**Tag:** `corporate`, `financial`

```
Goal:
Plan the conversion of a 120-vehicle mixed fleet (vans, cars, light trucks) owned by a Danish logistics company (Herning-based, regional delivery operations) from diesel to electric over 36 months. The company makes 800–1,200 local deliveries per day across Jutland.

Context:
The company has a fixed depot in Herning with a workshop and overnight parking for all vehicles. Current fleet average age is 4.5 years. A new EU road transport CO2 regulation requires measurable fleet emissions reduction by 2027. The company has no current EV experience.

Target users:
Operations director and fleet manager (internal planning). Logistics operations staff (implementation).

Scope (in):
- Vehicle replacement schedule and model selection (van and light truck categories)
- Charging infrastructure at Herning depot
- Driver training programme
- Electricity supply contract and tariff optimisation
- Total cost of ownership modelling vs. current diesel fleet
- Regulatory compliance milestone timeline

Scope (out):
- Public charging network (depot-only charging model — no reliance on public infrastructure)
- Hydrogen vehicles (not viable at this cost point — do not recommend)
- Fleet telematics or route optimisation software (separate IT programme)
- Expansion to other depot locations (Herning only)

Constraints:
- Budget: DKK 45M–60M over 36 months (capex + infrastructure)
- All vehicles must remain operational during transition — no gap in delivery capacity
- Must achieve 40% EV share by month 18 for EU compliance milestone
- Depot space for charging: 80 charging points maximum (physical constraint)

Success criteria:
- 100% electric fleet by month 36
- Total cost of ownership break-even vs. diesel within 5 years
- Zero delivery capacity reduction during transition
- CO2 reduction verified and reportable under EU taxonomy

Uncertainties:
- Battery range in cold Jutland winters may be 15–25% lower than rated — plan conservatively
- Electricity grid upgrade lead time from Energinet is 12–18 months — treat as a hard dependency risk
- EV van availability for large payload categories is limited — treat procurement as uncertain
```

---

### Prompt 09 — Open-Source Developer Tool (Tech / Community)

**Domain:** Developer tooling / open source  
**Stress:** `SelectScenarioTask`, `AssumptionsTask` — many valid implementation paths  
**Drift risk:** Scope expansion (tool → platform/ecosystem), business model drift (open source → SaaS without basis)  
**Tag:** `tech-product`, `adversarial-drift`

```
Goal:
Build and grow an open-source command-line tool that helps developers audit the dependency trees of Python projects for outdated packages, known vulnerabilities, and licence incompatibilities. The tool integrates with existing CI/CD pipelines and produces structured reports.

Context:
Two developers have been using an internal version of this tool at their employer for 18 months. They want to open-source it and build a community. They have no dedicated funding and will work on this evenings and weekends for the first year.

Target users:
Python developers and DevOps engineers using pip-based projects. Not data scientists, not package maintainers, not enterprise security teams (those have dedicated commercial tools already — do not position against them).

Scope (in):
- CLI tool design and feature set
- Dependency tree analysis (pip, requirements.txt, pyproject.toml)
- CVE database integration (OSV.dev, NVD)
- Licence compatibility matrix
- GitHub Actions integration
- Documentation and contributor guide
- Community building plan (Discord, GitHub Discussions)
- Sustainability model for maintaining the project long-term

Scope (out):
- SaaS or hosted version (explicitly excluded — open source only, no commercial product in this plan)
- Support for non-Python ecosystems (npm, cargo, etc.) — do not include in roadmap
- Enterprise sales or paid tiers
- Paid support contracts
- Investor funding

Constraints:
- Budget: USD 0 (evenings and weekends only, no capital)
- Two maintainers maximum for year 1
- Must be usable without any account, API key, or registration
- All data sources must be free and open

Success criteria:
- 500 GitHub stars within 6 months
- 50 active weekly users within 6 months
- First external contributor pull request merged within 3 months
- Project is self-sustaining (maintainers spend < 5 hours/week) by month 18

Uncertainties:
- Adoption in a saturated open-source tooling market is genuinely unknown — do not assume growth
- OSV.dev API reliability and completeness has gaps — treat CVE coverage as partial
```

---

### Prompt 10 — New Religious Community Centre (Community / Governance)

**Domain:** Community / cultural  
**Stress:** `GovernanceTask`, `StakeholderTask`, multi-constraint structured output  
**Drift risk:** Scope expansion (community centre → cultural hub), governance drift (informal → commercial)  
**Tag:** `community`, `governance-heavy`

```
Goal:
Plan the establishment of a community centre for a Somali-Danish community association in Aarhus, Denmark. The centre will provide meeting space, Danish language classes, youth activities, and a space for cultural events. The association has 340 registered members and has been operating informally for 8 years.

Context:
The association currently rents space ad hoc from churches and schools, which creates scheduling instability. They have identified a suitable property — a former community hall in Viby (15 minutes south of Aarhus centre) available for long-term lease at DKK 18,000/month. They have received a conditional grant from Aarhus Kommune of DKK 600,000 for startup costs, contingent on demonstrating organisational governance and a 3-year sustainability plan.

Target users:
Somali-Danish community members in Aarhus (primary). Secondary: Aarhus Kommune as funder and partner.

Scope (in):
- Formal organisational structure (vedtægter, board, governance)
- Property lease negotiation and fit-out plan
- Programme design: language classes, youth activities, cultural events
- Funding and sustainability model for years 1–3
- Grant compliance requirements for Aarhus Kommune
- Volunteer coordinator model (no paid staff in year 1)
- Community communication plan (Somali and Danish)

Scope (out):
- Commercial catering or café (not permitted under grant terms)
- External rental to non-member organisations (defer to year 2 pending licence)
- Political or religious instruction (explicitly excluded — the centre is secular and non-partisan)
- National expansion or federation with other associations

Constraints:
- Budget: DKK 600,000 grant + DKK 80,000 member contributions = DKK 680,000 startup
- Monthly rent DKK 18,000 — must be covered by year 2 without grant
- Grant requires formal governance documentation within 60 days of signing
- Secular and non-partisan operation is a hard requirement

Success criteria:
- Formal organisational registration (foreningsregistrering) complete within 90 days
- Centre operational within 6 months
- Danish language classes running with 40+ enrolled students by month 9
- Self-sustaining (covering monthly costs without external grants) by year 3
- Aarhus Kommune grant compliance report submitted on time

Uncertainties:
- Property lease negotiation outcome is unconfirmed — plan must present a fallback location option
- Volunteer availability is uncertain — do not assume full volunteer coverage; model a minimum viable team
- Second-year funding sources are unconfirmed — treat as a risk, not a given
```

---

## 4. Test Matrix

| # | Domain | Primary Stage Stress | Drift Risk | Adversarial? |
|---|--------|---------------------|------------|--------------|
| 01 | Community | Baseline | Scope expansion | No |
| 02 | Healthcare | Assessment + Review | Regulatory posture | No |
| 03 | Urban planning | Scenario selection | Priority drift | No |
| 04 | Small business | Assumptions + Criticism | Business model | No |
| 05 | Government ops | Governance + WBS | Confidence inflation | No |
| 06 | EdTech | Scenarios + Review | Customer drift | Yes — tempts institutional expansion |
| 07 | Crisis management | Premise attack | Scope expansion | No |
| 08 | Corporate ops | Cost + Gantt | Financial confidence | No |
| 09 | Open source | Assumptions | Business model drift | Yes — tempts SaaS conversion |
| 10 | Community/governance | Governance | Scope expansion | No |

---

## 5. How to Use This Suite

### Running a baseline
```
for each prompt in [01..10]:
    run_plan_pipeline(prompt, model_profile="baseline")
    record: completed | failed at task X | error type
```

### Running a comparison
```
for each model in [qwen-local, gemini-2.5, gemini-3.1]:
    for each prompt in [01..10]:
        result = run_plan_pipeline(prompt, model=model)
        drift_score = drift_evaluate(prompt, result)  # proposal 84
        record: completion_status, drift_score, task_failure_point
```

### What to look for
- Which tasks fail most often across prompts? → structural pipeline weakness
- Which drift types occur most often? → model-specific tendency
- Which prompts produce the most adversarial drift (06, 09)? → model discipline under temptation
- Do local models fail at different stages than cloud models? → model capability floor

---

## 6. Maintenance

- When a pipeline stage is changed, re-run the prompts that stress that stage
- When a new model profile is added, run all 10 prompts before declaring it stable
- When a drift detection type is added (proposal 82/84), re-run to establish baselines
- Add new prompts when new failure modes are identified — target 15 prompts by Q3 2026
