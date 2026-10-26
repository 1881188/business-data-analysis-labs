-- New SQLite queries for the normalized tables constructed by B21 main.py.
-- Original MySQL server/import scripts are read-only references.

-- select_columns
SELECT year,market,sale,profit FROM sale;

-- distinct_years
SELECT DISTINCT year FROM sale;

-- filter_2012
SELECT * FROM sale WHERE year=2012;

-- sort_year
SELECT * FROM sale ORDER BY year;

-- ratio_filter
SELECT *, 1.0*profit/NULLIF(sale,0) AS rate FROM sale WHERE 1.0*profit/NULLIF(sale,0)<.07;

-- date_and_case
SELECT trans_id, (CAST(strftime('%w',date) AS INTEGER)+6)%7 AS weekday, CASE WHEN (CAST(strftime('%w',date) AS INTEGER)+6)%7>=5 THEN '周末' ELSE '工作日' END AS weekday_group FROM trans WHERE date BETWEEN '1998-12-01' AND '1998-12-31' AND k_symbol='房屋贷款';

-- group_having
SELECT date,COUNT(*) AS records,AVG(amount_cents) AS mean_amount_cents,SUM(amount_cents) AS sum_amount_cents FROM trans GROUP BY date HAVING COUNT(*)>300;

-- join_cross
SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a CROSS JOIN table2 b;

-- join_inner
SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a INNER JOIN table2 b ON a.id=b.id;

-- join_left
SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a LEFT JOIN table2 b ON a.id=b.id;

-- join_right
SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table2 b LEFT JOIN table1 a ON a.id=b.id;

-- join_outer
SELECT a.id left_id,a.value left_value,b.id right_id,b.value right_value FROM table1 a LEFT JOIN table2 b ON a.id=b.id UNION ALL SELECT a.id,a.value,b.id,b.value FROM table2 b LEFT JOIN table1 a ON a.id=b.id WHERE a.id IS NULL;

-- in_subquery
SELECT trans_id FROM trans WHERE account_id IN (SELECT account_id FROM loans WHERE status='B');

-- correlated_exists
SELECT trans_id FROM trans t WHERE EXISTS (SELECT 1 FROM loans l WHERE l.status='B' AND l.account_id=t.account_id AND t.date<l.date);

-- non_equi_calendar_join
SELECT l.loan_id,COUNT(t.trans_id) records FROM loans l LEFT JOIN trans t ON l.account_id=t.account_id AND t.date<l.date AND t.date>=date(l.date,'-365 days') GROUP BY l.loan_id;

-- union_all
SELECT * FROM one UNION ALL SELECT * FROM two;

-- union_distinct
SELECT * FROM one UNION SELECT * FROM two;

CREATE TEMP TABLE lesson_test AS SELECT * FROM sale WHERE year IN (2010,2011);
-- create_table_as
SELECT * FROM lesson_test;

CREATE TEMP VIEW lesson_view AS SELECT * FROM sale;
-- create_view
SELECT * FROM lesson_view;

-- profile_180
SELECT c.card_id, COUNT(t.trans_id) AS records,
            SUM(CASE WHEN t.type='借' THEN t.amount_cents ELSE 0 END) AS debit_cents,
            SUM(CASE WHEN t.type='贷' THEN t.amount_cents ELSE 0 END) AS credit_cents,
            AVG(t.balance_cents) AS transaction_weighted_balance_cents
            FROM card_base c LEFT JOIN trans t ON c.account_id=t.account_id
              AND t.date<c.issued AND t.date>date(c.issued,'-180 days')
            GROUP BY c.card_id ORDER BY c.card_id;

-- profile_365
SELECT c.card_id, COUNT(t.trans_id) AS records,
            SUM(CASE WHEN t.type='借' THEN t.amount_cents ELSE 0 END) AS debit_cents,
            SUM(CASE WHEN t.type='贷' THEN t.amount_cents ELSE 0 END) AS credit_cents,
            AVG(t.balance_cents) AS transaction_weighted_balance_cents
            FROM card_base c LEFT JOIN trans t ON c.account_id=t.account_id
              AND t.date<c.issued AND t.date>date(c.issued,'-365 days')
            GROUP BY c.card_id ORDER BY c.card_id;

-- last_day
WITH last_dates AS (SELECT c.card_id, MAX(t.date) AS last_date FROM card_base c
        LEFT JOIN trans t ON c.account_id=t.account_id AND t.date<c.issued GROUP BY c.card_id)
        SELECT c.card_id, julianday(c.issued)-julianday(l.last_date) AS last_days,
          COUNT(t.trans_id) AS last_day_rows, AVG(t.balance_cents) AS last_day_balance_mean_cents,
          MIN(t.balance_cents) AS last_day_balance_min_cents, MAX(t.balance_cents) AS last_day_balance_max_cents
        FROM card_base c LEFT JOIN last_dates l ON c.card_id=l.card_id
        LEFT JOIN trans t ON c.account_id=t.account_id AND t.date=l.last_date
        GROUP BY c.card_id ORDER BY c.card_id;
