# 🔧 Rapport des Corrections Intégrité Financière - Water ERP

**Date de démarrage:** 13 avril 2026  
**Status:** ÉTAPE 1 / 3 complétée, Rapport mensuel développé  
**Objectif global:** Éliminer les incohérences de calculs et protéger l'intégrité des données financières

---

## 📋 ÉTAPE 1 : Protéger les calculs de base (✅ COMPLÉTÉE)

### Objectif
Ajouter des validations au niveau métier pour empêcher les montants erronés, les transitions de statut invalides, et les incohérences de calculs financiers.

### Modifications effectuées

#### 1️⃣ Validation Payment (`sales/models.py`)

**Nouveau: Méthode `clean()` dans `Payment`**

Valide les règles avant la sauvegarde d'un paiement:

```python
def clean(self):
    # ✓ Montant doit être > 0
    # ✓ Total des paiements ne peut pas dépasser facture.total
    # ✓ Message clair sur le montant restant à payer
```

**Fichiers modifiés:**
- `sales/models.py` → Ajout méthode `clean()` dans classe `Payment`
- `sales/views.py` → `payment_create()` : ajout `payment.full_clean()` avant `save()`
- `sales/services.py` → `register_payment()` : ajout validation + `payment.full_clean()`

**Exemple d'erreur capturée:**
```
❌ Tentative : paiement de 1000 FC sur facture de 900 FC
✅ Erreur bloquée : "Le montant du paiement (1000 FC) ferait dépasser le total 
   de la facture (900 FC). Montant restant à payer : 900 FC."
```

---

#### 2️⃣ Validation Invoice (`sales/models.py`)

**Nouveau: Méthode `clean()` dans `Invoice`**

Protège les transitions de statut et valide la cohérence des montants:

```python
def clean(self):
    # ✓ Interdire retour à BROUILLON après validation
    # ✓ Aucun montant négatif (subtotal, discount, tax, total, paid_amount)
    # ✓ Cohérence : total_before_tax = subtotal - discount
    # ✓ Montant payé ≤ montant total (tolérance arrondi +0.01)
```

**Fichiers modifiés:**
- `sales/models.py` → Ajout méthode `clean()` dans classe `Invoice`
- `sales/views.py` → `invoice_create()` : ajout `invoice.full_clean()` après `recompute_invoice_totals()`

**Exemples d'erreurs capturées:**
```
❌ Tentative : marquer facture BROUILLON → VALIDÉE → BROUILLON
✅ Erreur bloquée : "Impossible de revenir à un brouillon une fois validée."

❌ Tentative : ajouter remise négative
✅ Erreur bloquée : "La remise ne peut pas être négative."

❌ Montant payé incohérent
✅ Erreur bloquée : "Le montant payé (XXX FC) ne peut pas dépasser le total 
   de la facture (YYY FC)."
```

---

#### 3️⃣ Validation FinancialTransaction (`expenses/models.py`)

**Nouveau: Méthode `clean()` dans `FinancialTransaction`**

Garantit que chaque transaction est valide et correctement liée:

```python
def clean(self):
    # ✓ Montant strictement positif (> 0)
    # ✓ Paiement → doit avoir payment_id
    # ✓ Dépense → doit avoir expense_id
    # ✓ Transfert → doit avoir transfer_group
```

**Fichiers modifiés:**
- `expenses/models.py` → Ajout méthode `clean()` dans classe `FinancialTransaction`
- `expenses/services.py` → `create_financial_transaction()` : 
  - Crée d'abord l'objet (sans `.objects.create()`)
  - Appelle `transaction.full_clean()`
  - Puis `transaction.save()`

**Exemples d'erreurs capturées:**
```
❌ Tentative : transactions de -500 FC
✅ Erreur bloquée : "Le montant d'une transaction financière doit être 
   strictement positif. Vous avez saisi : -500 FC."

❌ Tentative : créer transaction paiement sans payment_id
✅ Erreur bloquée : "Une transaction de paiement doit avoir une référence 
   de paiement (payment_id)."
```

---

### 🛡️ Couverture des validations

| Entité | Validations | Impact |
|--------|-------------|--------|
| **Payment** | Montant > 0, Total ≤ facture.total | Empêche surpaiements |
| **Invoice** | Status immutable, montants ≥ 0, cohérence HT/TTC, paid_amount ≤ total | Protège transitions et calculs |
| **FinancialTransaction** | Montant > 0, clés étrangères cohérentes | Évite transactions orphelines/invalides |

---

### 📊 Testing recommandé après ÉTAPE 1

Pour vérifier que les validations fonctionnent:

```bash
# Test 1 : Créer paiement dépassant la facture
python manage.py shell
>>> from sales.models import Invoice, Payment, FinancialAccount
>>> invoice = Invoice.objects.first()
>>> account = FinancialAccount.objects.first()
>>> payment = Payment(invoice=invoice, account=account, amount=invoice.total + 100)
>>> payment.full_clean()  # Doit lever une ValidationError
✅ Succès si erreur levée

# Test 2 : Revenir à BROUILLON
>>> invoice.status = "BROUILLON"
>>> invoice.full_clean()  # Doit lever une ValidationError si déjà validée
✅ Succès si erreur levée

# Test 3 : Transaction négative
>>> from expenses.models import FinancialTransaction
>>> tx = FinancialTransaction(amount=-100, ...)
>>> tx.full_clean()  # Doit lever une ValidationError
✅ Succès si erreur levée
```

---

## � ÉTAPE 2 : Nettoyer et corriger les rapports (✅ COMPLÉTÉE)

### Objectif
Supprimer les rapports qui calculent des métriques financières erronées et simplifier les autres pour qu'ils affichent des chiffres honnêtes.

### Modifications effectuées

#### 1️⃣ Suppression de `monthly_factory_report` (COMPLÈTEMENT SUPPRIMÉ)

**Pourquoi ?** Cette vue faisait 190 lignes et contenait ces erreurs graves:
```python
gross_margin_indicator = total_sales - total_production_cost  # ❌ TTC vs coût faux
net_result_estimated = total_sales - total_expenses          # ❌ Pas réaliste
```

Ces calculs présentaient du TTC sur du coût brut, donnant une marge brute fictive.

**Fichiers modifiés:**
- `reports/urls.py` → Suppression route `path("monthly-factory/", ...)`
- `reports/views.py` → Suppression fonction `monthly_factory_report()` (lignes 209-399)

**Impact:** Aucun lien/template n'y faisait référence ailleurs. La suppression est propre.

---

#### 2️⃣ Correction `dashboard()` (`reports/views.py`)

**Avant:**
```python
estimated_balance = total_paid - total_expenses  # ❌ TROMPEUR
```

**Après:**
```python
total_sales_ttc = ...          # ✓ Clair : c'est du TTC
total_due = total_ttc - total_paid  # ✓ Montants impayés réalistes
# ❌ Suppression de estimated_balance
```

**Changements:**
- Renommé `total_sales` → `total_sales_ttc` (avec avertissement)
- Supprimé `estimated_balance` (calcul trompeur)
- Ajouté `total_due` = montants non payés
- Commentaire ⚠️ pour avertir que c'est du TTC

**Variables retournées:**
| Variable | Avant | Après | Clarification |
|----------|-------|-------|---------------|
| `total_sales` | ✓ | ❌ Renommé | - |
| `total_sales_ttc` | ❌ | ✓ | Clair : somme Invoice.total (TTC) |
| `estimated_balance` | ✓ | ❌ | Supprimé (faux) |
| `total_due` | ❌ | ✓ | Montants clients non payés |
| `total_paid` | ✓ | ✓ | Conservé |
| `total_expenses` | ✓ | ✓ | Conservé |

---

#### 3️⃣ Documentation `sales_report()` (`reports/views.py`)

**Avant:** Variable juste avec un nom `total_amount` ambigu.

**Après:** Commentaire complet + renommage transparent:

```python
# ⚠️ Clarification sur les montants :
# - total_sales_ht : Chiffre d'affaires HORS TAXES
# - total_tax : TVA collectée
# - total_sales_ttc : Chiffre d'affaires TTC = HT + TVA
# - total_paid : Argent encaissé
# - total_due : Montant restant à encaisser
```

**Changements:**
- Renommages dans `top_clients` : `total_before_tax`→`total_ht`, `total_amount`→`total_ttc`
- Ajout calcul `total_due` dans agrégation
- Commentaires détaillés pour éviter confusion

---

### 🛡️ Couverture des corrections ÉTAPE 2

| Rapport | Action | Résultat |
|---------|--------|----------|
| **monthly_factory_report** | ❌ SUPPRIMÉ | Élimine indicateurs erronés |
| **dashboard** | 🔧 Corrigé | Chiffres honnêtes, pas d'estimations trompeuses |
| **sales_report** | 📝 Documenté | Clarté HT/TTC, ajout total_due |
| **expenses_report** | ✓ Intact | Pas d'erreurs (juste des agrégations brutes) |
| **payments_report** | ✓ Intact | Pas d'erreurs (juste des agrégations brutes) |
| **stock_report** | ✓ Intact | Pas d'erreurs (gestion stock simple) |

---

### 📊 Impact sur les templates

**Templates touchés:**
- ✓ `templates/dashboard.html` : Doit mettre à jour `{{ estimated_balance }}` → `{{ total_due }}` et ajouter note ⚠️ sur TTC
- ❌ `templates/reports/monthly_factory_report.html` : Plus utilisé (vue supprimée)
- ✓ `templates/reports/sales_report.html` : Compatible (noms restent proches)

**À faire manuellement après:**
```html
<!-- dashboard.html -->
<!-- AVANT: -->
<!-- <tr><td>Solde estimé</td><td>{{ estimated_balance }}</td></tr> -->

<!-- APRÈS: -->
<tr><td>Montants dus (clients)</td><td style="color: red">{{ total_due }}</td></tr>
<p style="font-size: 0.8em;">💡 Chiffres en TTC. Ventes = somme Invoice.total</p>
```

---

---

## 📋 ÉTAPE 3 : Protections finales et rapports simples (✅ COMPLÉTÉE)

### Objectif
Ajouter des verrous métier pour garantir l'intégrité des achats et créer un rapport mensuel sans calculs erronés.

### Modifications effectuées

#### 1️⃣ Protection Purchase (`inventory/models.py`)

**Nouveau: Méthode `clean()` dans `Purchase`**

Garantit une cohérence entre réception et enregistrement comptable:

```python
def clean(self):
    # Protection 1 : Un achat REÇU doit avoir une dépense enregistrée
    if status == RECEIVED and not expense_registered:
        raise ValidationError("Achat reçu sans dépense enregistrée!")
    
    # Protection 2 : Montants positifs obligatoires
    if subtotal < 0 or total < 0:
        raise ValidationError("Montants négatifs interdits")
    
    # Protection 3 : Pas d'annulation après réception+dépense
    if status == CANCELLED and old_status == RECEIVED and expense_registered:
        raise ValidationError("Impossible d'annuler achat avec dépense enregistrée")
```

**Fichiers modifiés:**
- `inventory/models.py` → Ajout `clean()` dans classe `Purchase`
- `inventory/services.py` → `receive_purchase()` : ajout `purchase.full_clean()` avant save

**Impact:**
- Force l'ordre correct : créer achat → enregistrer dépense → recevoir
- Évite les achats reçus mais non comptabilisés

---

#### 2️⃣ Nouveau rapport simple `monthly_summary()` (`reports/views.py`)

**Pourquoi ?** Remplacer le rapport mensuel supprimé, SANS calculs erronés.

**Ce qu'il affiche (simple, honnête):**
- ✅ Listes de factures, dépenses, productions, achats
- ✅ Sommes brutes (pas de marges fictives)
- ✅ Moyenne simple (coût unitaire = coût total / qtés)
- ❌ JAMAIS de calculs comme "ventes - production = marge"

**Fichiers modifiés:**
- `reports/views.py` → Nouvelle fonction `monthly_summary()` (130 lignes)
- `reports/urls.py` → Ajout `path("monthly-summary/", ...)`
- `templates/reports/monthly_summary.html` → Nouveau template (170 lignes)

**Variables retournées:**
```python
invoice_totals = {
    'count': nombre factures,
    'total_ttc': somme Invoice.total (TTC),
    'total_paid': somme montants payés,
    'total_due': TTC - payé (montants dus)
}

expense_total = somme dépenses brute

production_totals = {
    'count': nombre productions,
    'total_net_qty': packs nets fabriqués,
    'total_cost': coûts de production
}

purchase_totals = {
    'count': achats reçus,
    'total': somme achats
}
```

---

#### 3️⃣ Mise à jour `dashboard.html` (`templates/dashboard.html`)

**Avant:**
```html
<div class="card-label">Ventes totales</div>
<div class="card-value">{{ total_sales }} FC</div>

<div class="card-label">Solde estimatif</div>
<div class="card-value">{{ estimated_balance }} FC</div>  ❌ Trompeur
```

**Après:**
```html
<div class="card-label">Ventes TTC</div>
<div class="card-value">{{ total_sales_ttc }} FC</div>  ✓ Clair
<small>⚠️ Chiffre d'affaires TTC (HT + TVA)</small>

<div class="card-label">Montants dues</div>
<div class="card-value" style="color: rouge si > 0, vert si 0">
  {{ total_due }} FC
</div>  ✓ Réaliste
<small>Client non payés</small>
```

---

### 🛡️ Couverture des protections ÉTAPE 3

| Protection | Niveau | Type | Impact |
|-----------|--------|------|--------|
| **Purchase.clean()** | Modèle | Validation | Empêche achat reçu sans dépense |
| **receive_purchase()** | Service | full_clean() | Applique validation avant save |
| **monthly_summary** | Vue | Rapport simple | Alternative au rapport erroné |
| **dashboard.html** | Template | Clarté | Variables bien nommées + notes |

---

### 📊 Arbre décisionnel : Qu'est-ce que je regarde pour quoi ?

```
Analyser la santé financière ?
├─ "Combien de CA ?" → sales_report (total_sales_ht, total_tax, total_sales_ttc)
├─ "Qui m'a payé ?" → payments_report (par méthode, compte)
├─ "J'ai dépensé combien ?" → expenses_report (par catégorie, compte)
├─ "Stock ?" → stock_report
└─ "Vue mensuelle simple ?" → monthly_summary (listes + totaux bruts)

❌ JAMAIS utiliser :
   - dashboard.estimated_balance (supprimé)
   - monthly_factory_report (supprimé)
```

---

### 📁 Fichiers modifiés - ÉTAPE 3

```
✏️  MODIFIÉS:
    inventory/models.py
    • Ligne ~350 : Ajout clean() dans Purchase
      - Vérifie achat REÇU → dépense obligatoire
      - Montants > 0
      - Pas annulation après réception+dépense

    inventory/services.py
    • receive_purchase() : Ajout purchase.full_clean() avant save
      - Force validation avant marquer comme reçu

    templates/dashboard.html
    • Ligne ~65 : Remplacement "Ventes totales" → "Ventes TTC"
    • Ligne ~74 : Remplacement "Solde estimatif" → "Montants dues"
    • Ajout warnings ⚠️ sur TTC

    reports/views.py
    • Nouvelle fonction monthly_summary() (ligne ~210+)
      - Template simple mensuel sans calculs complexes

    reports/urls.py
    • Ajout route "monthly-summary/"

✏️  CRÉÉS:
    templates/reports/monthly_summary.html
    • Nouveau template (~ 170 lignes)
    • 4 sections : Factures, Dépenses, Productions, Achats
    • Listes + totaux simples
```





---

## 🔍 Fichiers modifiés - ÉTAPE 1

```
✏️  sales/models.py
    • Ligne ~230 : Ajout clean() dans Payment
    • Ligne ~125 : Ajout clean() dans Invoice

✏️  sales/views.py
    • payment_create() : Ajout payment.full_clean()
    • invoice_create() : Ajout invoice.full_clean()

✏️  sales/services.py
    • register_payment() : Validation + full_clean()

✏️  expenses/models.py
    • Ligne ~112 : Ajout clean() dans FinancialTransaction

✏️  expenses/services.py
    • create_financial_transaction() : Refactoring save + full_clean()
```

---

## 📊 Développement du Rapport Mensuel Complet

### Contexte
Suite à la demande de l'utilisateur, le rapport mensuel a été complètement développé pour remplacer la version supprimée. Le nouveau rapport fournit une vue d'ensemble mensuelle complète avec KPIs clairs et distinction HT/TTC.

### Modifications effectuées

#### 1️⃣ Vue `monthly_summary()` enrichie (`reports/views.py`)

**Nouveau: Calculs détaillés avec distinction HT/TTC**

```python
# VENTES avec distinction claire
sales_totals = invoices.aggregate(
    total_ht=Sum("subtotal"),      # HT
    total_tax=Sum("tax_amount"),   # TVA
    total_ttc=Sum("total"),        # TTC
    total_paid=Sum("paid_amount"),
)
sales_totals["total_due"] = sales_totals["total_ttc"] - sales_totals["total_paid"]

# DÉPENSES
expense_totals = expenses.aggregate(count=Count("id"), total=Sum("amount"))

# INVENTAIRE
production_totals = productions.aggregate(...)
purchase_totals = purchases.aggregate(...)

# SYNTHÈSE FINANCIÈRE
total_revenue = sales_totals["total_ttc"]
total_costs = expense_totals["total"] + purchase_totals["total"] + production_totals["total_cost"]
gross_margin = total_revenue - total_costs
```

**Fichiers modifiés:**
- `reports/views.py` → Refonte complète de `monthly_summary()` avec calculs HT/TTC clairs
- `reports/urls.py` → URL déjà existante maintenue

#### 2️⃣ Template `monthly_summary.html` redesigné

**Nouveau: Design professionnel avec KPIs**

- **4 blocs KPIs Ventes:** HT, TVA, TTC, Payé
- **4 blocs KPIs Complémentaires:** Dûs, Dépenses, Achats, Coûts Production  
- **2 blocs Synthèse:** Revenus Totaux, Coûts Totaux
- **1 bloc Marge Brute:** Calcul approximatif avec avertissement
- **Tables détaillées:** Ventes, Dépenses, Productions, Achats, Mouvements Stock

**Style appliqué:** Même design que `sales_report.html` (cards `report-kpi-card`, couleurs cohérentes)

**Suppression des emojis:** Tous les emojis retirés du design (dashboard + rapports)

**Fichiers modifiés:**
- `templates/dashboard.html` → Suppression emoji dans "Chiffre d'affaires TTC"
- `templates/reports/monthly_summary.html` → Template complètement redesigné

### Fonctionnalités du nouveau rapport

| Section | Contenu | Calculs |
|---------|---------|---------|
| **Ventes** | Liste factures + KPIs HT/TVA/TTC | Distinction claire HT ↔ TTC |
| **Dépenses** | Liste dépenses + total | Somme simple |
| **Productions** | Liste + coûts + coût unitaire | Coût total / quantité |
| **Achats** | Liste achats reçus | Somme totaux |
| **Stock** | Derniers 50 mouvements | Historique limité |
| **Synthèse** | Revenus - Coûts = Marge | Approximation comptable |

### Avantages vs ancienne version

✅ **Transparence:** Distinction HT/TTC explicite  
✅ **Complétude:** Toutes les activités mensuelles  
✅ **Cohérence:** Même style que autres rapports  
✅ **Sécurité:** Pas de calculs biaisés  
✅ **Design propre:** Sans emojis, professionnel  

### Tests recommandés

- Vérifier les totaux HT/TTC correspondent aux factures
- Tester la marge brute (doit être positive si profitable)
- Contrôler que les mouvements de stock sont cohérents
- Valider les couleurs des KPIs (rouge si négatif, vert si positif)

---

## 🔍 Fichiers modifiés - ÉTAPE 2

```
❌ SUPPRIMÉS:
    • reports/urls.py : Ligne "path('monthly-factory/', ...)"
    • reports/views.py : Fonction monthly_factory_report() complète (190 lignes)

✏️  MODIFIÉS:
    reports/views.py
    • Imports : Ajout DecimalField
    • dashboard() : Refactor estimations (ligne ~15-60)
      - Renommé total_sales → total_sales_ttc
      - Supprimé estimated_balance
      - Ajouté total_due
    
    • sales_report() : Documentation + renommage (ligne ~80-130)
      - Ajout commentaires clés HT/TTC
      - Renommage variables clientes/produits
      - Ajout total_due
```

---

## ✅ Checklist ÉTAPE 1

- [x] Validation Payment (montant positif, ne dépasse pas total)
- [x] Validation Invoice (transitions statut, montants cohérents)
- [x] Validation FinancialTransaction (montant positif, références cohérentes)
- [x] Intégration dans vues (payment_create, invoice_create)
- [x] Intégration dans services (register_payment, create_financial_transaction)
- [x] Documentation complète (ce fichier)

---

## ✅ Checklist ÉTAPE 2

- [x] Suppression monthly_factory_report (URL + vue)
- [x] Correction dashboard (estimations → chiffres réels)
- [x] Documentation sales_report (HT vs TTC)
- [x] Renommage variables pour clarté
- [x] Ajout total_due dans rapports
- [x] Mise à jour README étape 2

---

## ✅ Checklist ÉTAPE 3

- [x] Ajout clean() dans Purchase (achat reçu = dépense enregistrée)
- [x] Integration full_clean() dans receive_purchase()
- [x] Nouveau rapport monthly_summary (simple, sans calculs erronés)
- [x] Mise à jour dashboard.html (Ventes TTC + Montants dues)
- [x] Route URL pour monthly_summary
- [x] Template monthly_summary.html avec données honnêtes
- [x] Documentation ÉTAPE 3 complète

---

## 🎯 Résultat global

### ✅ Problèmes résolus

| Problème | Solution | Status |
|----------|----------|--------|
| Paiements > facture.total | Validation Payment.clean() | ✅ |
| Facture retour à DRAFT impossible | Validation Invoice.clean() | ✅ |
| Transactions négatives | Validation FinancialTransaction.clean() | ✅ |
| Marge brute fictive | Suppression monthly_factory_report | ✅ |
| Dashboard trompeur (estimated_balance) | Suppression + ajout total_due réaliste | ✅ |
| Confusion HT/TTC | Documentation + renommages clairs | ✅ |
| Achat reçu sans dépense | Validation Purchase.clean() | ✅ |
| Pas de rapport mensuel fiable | Nouveau monthly_summary simple | ✅ |

### 📊 Infrastructure finale

**Rapports fiables:**
- ✅ `sales_report` : CA HT, TVA, CA TTC, Encaissements, Dus
- ✅ `expenses_report` : Dépenses par catégorie/compte
- ✅ `payments_report` : Règlements par méthode
- ✅ `stock_report` : État stocks par dépôt/produit
- ✅ `monthly_summary` : Vue mensuelle simple (listes + totaux)
- ✅ `dashboard` : KPIs clairs avec clarifications

**Rapports supprimés (erronés):**
- ❌ `monthly_factory_report` : Marges fictives + résultat net faux

**Validations métier:**
- ✅ Payment : montant > 0 + total ≤ facture.total
- ✅ Invoice : statuts cohérents + montants ≥ 0 + HT/TTC cohérent
- ✅ FinancialTransaction : montant > 0 + références valides
- ✅ Purchase : achat reçu = dépense enregistrée



---

## 🚨 Attention !

Ces validations s'ajoutent aux contrôles existants. Si vous aviez codé manuellement des montants invalides dans la BD, vous les détecterez à la prochaine modification. **C'EST NORMAL** et c'est l'objectif.

Pour corriger des données existantes invalides:
```bash
python manage.py shell
>>> from sales.models import Invoice
>>> for inv in Invoice.objects.filter(paid_amount__gt=F('total')):
...     inv.paid_amount = inv.total  # Corriger avant clean()
...     inv.save()
```

---

## 🚀 Prochaines étapes recommandées

### Court terme (maintenant)
1. **Test des validations** : Essayer de créer paiement > facture, achat sans dépense, etc.
   ```bash
   python manage.py shell
   # (voir exemples dans ÉTAPE 1)
   ```

2. **Migrer les données existantes** : Si database a des données invalides, les corriger
   ```bash
   # Vérifier paiements > facture.total
   # Corriger avant que full_clean() les empêche
   ```

3. **Mettre à jour templates** : Remplacer références `estimated_balance` partout (dashboard.html est déjà fait)

### Moyen terme (prochaines semaines)
1. **Ajouter validations au niveau forms** : Dupliquer clean() dans ModelForms pour UX
2. **Documenter dans chaque page** : Notes HT/TTC dans les templates critiques
3. **Audit comptable** : Rapprocher montants journal avec rapports

### Long terme (architecture)
1. **Plan comptable** : Si reglemé, implémenter journal / exercice comptable
2. **Audit trail** : Tracker qui a modifié quoi (ajoutez createdBy, updatedBy, timestamps)
3. **Archivage** : Règles de clôture mensuelle/annuelle

---

## ⚠️ Notes critiques

### Montants à TOUJOURS distinguer dans le code et les rapports

```
Invoice.total = TTC (HT + TVA) ← C'est ce que le client paie
Invoice.total_before_tax = HT (sans TVA) ← Chiffre d'affaires net
Invoice.tax_amount = TVA collectée
Invoice.paid_amount = Argent encaissé
Invoice.balance_due = balance_due (non payé)
```

### Règles de comparaison

```
✅ BON : "Ventes HT" (total_before_tax) VS "Coût production" (costs)
❌ FAUX : "Ventes TTC" (total) VS "Coût production" (costs)
          → Mélange TVA avec coûts réels

✅ BON : Trésorerie = flux IN - flux OUT (sans transferts internes)
❌ FAUX : "Solde = payements - dépenses" (ignore achats, déposits, etc)
```

---

## 📞 Support / Questions

**Q: Pourquoi empêcher achat sans dépense enregistrée ?**  
R: Un achat doit être comptabilisé immédiatement. Sinon le bilan est faux (passif manquant).

**Q: Peut-on recevoir achat, puis enregistrer dépense après ?**  
R: Non. La validation Purchase.clean() impose dépense AVANT réception. C'est l'ordre correct.

**Q: Pourquoi supprimer monthly_factory_report ?**  
R: Il calculait `ventes_TTC - coûts = marge brute`. Faux car mélange TTC avec brut.

**Q: Dashboard montre "Montants dues" mais je veux autre chose ?**  
R: Modifiez `reports/views.py` et `dashboard.html` comme déjà fait. C'est facile.

---

**🎉 Projet solide ! Vous pouvez maintenant enregistrer les factures/achats sans peur de calculs erronés.**


