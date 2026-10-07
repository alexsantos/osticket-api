-- Index on ost_ticket.updated for GET /tickets?updated_after=...&updated_before=...
--
-- Stock osTicket indexes ost_ticket.created but not ost_ticket.updated, so the
-- date filters scan the whole ticket table. Run this once per osTicket database
-- as a user with ALTER privilege on ost_ticket (the API's own user only needs
-- read/write access and must not run DDL).
--
-- Works on MariaDB 5.5+ and MySQL 5.5+, and is idempotent: the index is only
-- added when it is missing (checked via information_schema, since
-- `ADD INDEX IF NOT EXISTS` needs MariaDB 10.0.2+ and does not exist in MySQL).
-- The distinctive name `api_updated` avoids clashing with any index a future
-- osTicket upgrade might add.
--
-- Locking: MariaDB 10.0+ and MySQL 5.6+ build the index online without blocking
-- reads or writes. MariaDB/MySQL 5.5 build it in place too, but block writes to
-- ost_ticket while it runs (a few seconds for a few hundred thousand tickets).
SET @api_updated_ddl = (
    SELECT IF(COUNT(*) = 0, 'ALTER TABLE ost_ticket ADD INDEX api_updated (updated)', 'DO 0')
    FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'ost_ticket' AND index_name = 'api_updated'
);
PREPARE api_updated_stmt FROM @api_updated_ddl;
EXECUTE api_updated_stmt;
DEALLOCATE PREPARE api_updated_stmt;
