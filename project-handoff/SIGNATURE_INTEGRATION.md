# Signature Integration

Seeds can be cryptographically signed using the Seed-Class Intelligence Architecture (SCIA) protocol.

### Signing Protocol
* The seed text and ID are combined into a digest.
* The user signs the digest using their local passphrase.
* The signature verification page (`/seeds/verify/<sig_id>`) checks:
  * Signature authenticity
  * Original text integrity
  * Author credentials
  * Supersession status (whether a newer version of the seed has been confirmed)
