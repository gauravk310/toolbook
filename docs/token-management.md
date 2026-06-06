# Token Management

---

### `set-token`
Store a secret token in the Toolbook environment (`~/.toolbook/.env`).

```bash
toolbook set-token <TOKEN_NAME> <TOKEN_VALUE>
```

**Example:**
```bash
toolbook set-token GITHUB_TOKEN ghp_abc123xyz456
```

---

### `show-tokens`
List all configured token names (values are never shown).

```bash
toolbook show-tokens
```

**Example:**
```bash
toolbook show-tokens
# Configured Tokens:
#   - GITHUB_TOKEN
```

---

## Python API

Tokens are stored in `~/.toolbook/.env` and loaded automatically by Toolbook at startup.
You can read a stored token in your own code using the `get_token` utility:

```python
from toolbook.utils import get_token

token = get_token("GITHUB_TOKEN")
print(token)  # ghp_abc123xyz456
```
