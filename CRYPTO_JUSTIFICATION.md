# CRYPTO_JUSTIFICATION.md

## Cryptographic Design Justification — SecureMoney
**Arusha Technical College | ICT Department | February 2026**

---

## 1. Why AES-256-GCM Over Other Modes?

### AES-CBC (Cipher Block Chaining) — Rejected
CBC provides confidentiality but **no integrity or authenticity**.
Without a separate MAC (e.g., HMAC-SHA256), an attacker can perform
**padding oracle attacks** (Vaudenay, 2002) and **bit-flipping attacks**
without detection. Implementing CBC+MAC correctly is error-prone.

### AES-ECB (Electronic Codebook) — Rejected
ECB encrypts identical plaintext blocks to identical ciphertext blocks,
producing **patterns** in encrypted data. The "ECB penguin" effect
(identifiable structure in encrypted images) demonstrates why ECB is
categorically insecure for variable or structured data.

### AES-CTR (Counter Mode) — Rejected (alone)
CTR provides confidentiality and parallelism but, like CBC, **no
authenticity**. Nonce reuse in CTR mode is catastrophic: two ciphertexts
encrypted with the same nonce and key reveal their XOR, enabling
full plaintext recovery.

### AES-256-GCM — Chosen ✅

GCM (Galois/Counter Mode) is specified in **NIST SP 800-38D** (Dworkin, 2007)
and combines:

| Property | Mechanism |
|---|---|
| **Confidentiality** | AES-CTR encryption |
| **Integrity** | GHASH universal hash function (GF(2¹²⁸)) |
| **Authenticity** | 128-bit authentication tag |
| **AEAD** | Additional Authenticated Data (AAD) binds ciphertext to a record |

**Key advantages for SecureMoney:**

1. **Single-pass AEAD**: One algorithm provides both encryption and authentication,
   eliminating the "MAC-then-Encrypt / Encrypt-then-MAC" dilemma and its
   associated implementation pitfalls (Bellare & Namprempre, 2000).

2. **Parallelizable**: GCM's CTR mode is parallelizable, meeting NFR-02
   (< 3 second transaction processing) even under load (NFR-06: 50+ users).

3. **NIST-approved**: Mandated by FIPS 140-2/3 for U.S. government use;
   de facto standard for TLS 1.3, SSH, and financial APIs worldwide.

4. **Authenticated Associated Data**: Transaction records bind the
   ciphertext to a database record ID via AAD, preventing ciphertext
   transplantation attacks (attacker swapping encrypted amounts between records).

5. **96-bit random nonce**: Per NIST SP 800-38D §8.2, the recommended
   nonce length of 96 bits maximises the GHASH security bound.
   With a CSPRNG and 96-bit nonces, the probability of nonce collision
   across 2³² encryptions is approximately 2⁻³³ — negligible.

---

## 2. Why PBKDF2-HMAC-SHA256 for Password Hashing?

**NIST SP 800-132** recommends PBKDF2 for password-based key derivation.
SecureMoney uses **600,000 iterations** (OWASP 2023 recommendation for SHA-256)
to impose significant computational cost on offline brute-force attacks.

| Parameter | Value | Justification |
|---|---|---|
| PRF | HMAC-SHA256 | NIST-approved, hardware-accelerated |
| Salt length | 256 bits | Eliminates rainbow tables, per NIST |
| Iteration count | 600,000 | ~0.5s on modern CPU; ~500 years for 10⁶ common passwords on GPU |
| Output length | 256 bits | Matches AES-256 key size; colision resistant |

**Alternatives considered:**
- **bcrypt**: Fixed 72-character password limit; not recommended for new systems.
- **scrypt**: Memory-hard; better against ASICs, but not FIPS-approved.
- **Argon2id**: Winner of PHC 2015; preferred for new systems where FIPS is not required.
  *For this academic/FIPS-aligned project, PBKDF2 is the correct choice.*

---

## 3. Key Architecture

```
MASTER_KEY_HEX (env var, 256-bit)
        │
        ▼
PBKDF2(master_key + context, user_salt, 10,000 iter)
        │
        ├──► "account_balance"     → Balance encryption key (per user)
        ├──► "transaction_amount"  → Amount encryption key (per transaction)
        └──► "personal_info"       → PII encryption key (per user)
```

This **key hierarchy** ensures:
- Compromise of one derived key does not expose others (key isolation).
- The master key is never stored in the database.
- Key rotation only requires re-deriving all leaf keys from a new master key.

---

## References

- Daemen, J. & Rijmen, V. (2002). *The Design of Rijndael: AES — The Advanced Encryption Standard*. Springer.
- McGrew, D. & Viega, J. (2004). *The Galois/Counter Mode of Operation (GCM)*. NIST submission.
- Dworkin, M. (2007). *NIST SP 800-38D: Recommendation for Block Cipher Modes of Operation: GCM*. NIST.
- NIST FIPS PUB 197 (2001). *Advanced Encryption Standard (AES)*.
- NIST SP 800-132 (2010). *Recommendation for Password-Based Key Derivation*.
- Bellare, M. & Namprempre, C. (2000). *Authenticated Encryption: Relations among notions and analysis of the generic composition paradigm*. ASIACRYPT 2000.
- OWASP (2023). *Password Storage Cheat Sheet*. https://cheatsheetseries.owasp.org/
- Vaudenay, S. (2002). *Security Flaws Induced by CBC Padding*. EUROCRYPT 2002.
