# Price model selection and held-out evaluation (MODEL-04 / MODEL-05)

Owner: Mykolaichuk Nazar. Milan and Florence only; Venice was not downloaded, configured,
queried or used. Code: `airbnb/price_model.py`, `notebooks/07_train_model.py`.

## 1. Predeclared plan (committed before any validation result was read)

### Data roles

| Role | Rows | Used for |
|---|---|---|
| Subtrain | official `train` rows (split `airbnb-v1`) whose `SHA-256("airbnb-v1-model-selection" \| city \| listing_id)` unit is ≥ 0.20 | fitting preprocessing, category grouping, the validation baseline and every candidate |
| Validation | the other official `train` rows (unit < 0.20) | comparing candidates |
| Official test | persisted `evaluation_split = 'test'` rows | read once, by stage `final`, after the selection record is locked |

The `select` stage loads only `evaluation_split = 'train'` rows. The validation baseline is the
required `room_type × accommodates` median lookup **refitted on subtrain**, not the persisted
`airbnb-v1` lookup (which saw validation rows).

### Features and preprocessing

See [model_feature_review.md](model_feature_review.md) ("Final allowlist (price-v1)"). Every
fitted step is inside one scikit-learn pipeline (`TransformedTargetRegressor` → `Pipeline` →
`ColumnTransformer`), so it is fitted only on the rows passed to `fit`.

- Target: `log1p(price_eur)`; predictions are `expm1` back to EUR.
- `property_type`: levels with < 50 fit rows → `__other__`; missing → `__missing__`.
- Other categoricals (room type and the booleans): every fit-row level kept; unseen → `__other__`.
- One-hot with `handle_unknown="ignore"`: an unseen level never raises.
- Numerics: cap at the fit-row p99; `log1p` on `minimum_nights` and `dist_center_km`; fit-row
  median imputation (+ missing indicator, except review scores); standard scaling for ridge.

### Candidates (8 fits, fixed seed 20261111)

| Family | Model | Search space |
|---|---|---|
| `ridge_log` | `Ridge` on the scaled, one-hot design | `alpha` ∈ {0.1, 1, 10, 100} |
| `hgb_log` | `HistGradientBoostingRegressor` (scikit-learn 1.7.2, no new dependency), `learning_rate` 0.05, `min_samples_leaf` 40, `l2_regularization` 1.0, no early stopping | `max_leaf_nodes` ∈ {15, 31} × `max_iter` ∈ {200, 400} |

### Selection rule

1. Within each family, take the candidate with the lowest pooled (Milan+Florence) validation MAE.
2. A family qualifies only if that candidate beats the subtrain baseline by ≥ 5 % in Milan,
   in Florence **and** pooled.
3. Choose the simplest qualifying family (ridge < gradient boosting) unless the more complex
   one beats it by ≥ 3 % in Milan, in Florence and pooled.
4. If no family qualifies, stop and report; do not evaluate on test.

The rule, candidate list, features and preprocessing are hashed into `spec_sha256`. Stage
`final` refuses to run if the code's `spec_sha256` differs from the locked record.
