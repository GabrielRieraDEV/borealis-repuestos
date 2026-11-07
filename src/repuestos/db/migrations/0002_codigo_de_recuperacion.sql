-- Migración 0002: código de recuperación de la clave de la dueña (hash scrypt; vacío = no generado).
INSERT INTO settings (key, value) VALUES ('owner_recovery_hash', '');
