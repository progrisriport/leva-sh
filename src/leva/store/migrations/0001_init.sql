CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE entry (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    section TEXT,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    summary TEXT NOT NULL,
    path TEXT,
    has_man INTEGER NOT NULL,
    curated INTEGER NOT NULL,
    explain TEXT NOT NULL,
    rank INTEGER NOT NULL
);

CREATE UNIQUE INDEX entry_key ON entry (name, IFNULL(section, ''), origin);
CREATE INDEX entry_name_rank ON entry (name, rank);

CREATE TABLE alias (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    alias TEXT NOT NULL,
    PRIMARY KEY (entry_id, alias)
);

CREATE INDEX alias_alias ON alias (alias);

CREATE TABLE doc_section (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    heading TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE example (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    id TEXT NOT NULL,
    description TEXT NOT NULL,
    cmd TEXT NOT NULL,
    source TEXT NOT NULL,
    verified TEXT NOT NULL,
    danger TEXT,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE note (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE subcommand (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    name TEXT NOT NULL,
    summary TEXT NOT NULL,
    entry_name TEXT,
    source TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE related (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE intent (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    ord INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (entry_id, ord)
);

CREATE TABLE content_item (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE VIRTUAL TABLE search_fts USING fts5 (
    name,
    intents,
    summary,
    body,
    content = '',
    tokenize = 'unicode61 remove_diacritics 2'
);
