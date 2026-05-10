"""
Data layer for demand model.
realization_report + paid_storage превращаем в недельный
временной ряд (nm_id * week)

get_full_weekly_panel() возвращает полную сетку без
пропусков тк модель может посчитать что пропуски - 0 продаж
"""
import os
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
ENGINE = create_engine(os.getenv("DATABASE_URL"))


def get_weekly_demand() -> pd.DataFrame:
    """
    Недельные продажи на уровне (nm_id, week).

    Возвращает только недели где были транзакции — для полной сетки
    используй get_full_weekly_panel().

    units = SUM(quantity), что автоматически вычитает возвраты внутри
    doc_type_name='Продажа' (там бывают строки с отрицательным quantity).
    """
    sql = text("""
        SELECT
            nm_id,
            date_trunc('week', sale_dt)::date          AS week, -- возвращает начало недели - синтаксис PostgreSQL. ::date - конвертирует timestamp в date
            SUM(quantity)                               AS units,
            SUM(ppvz_for_pay)                           AS revenue_rub,
            CASE WHEN SUM(quantity) > 0
                 THEN SUM(retail_price_withdisc_rub * quantity)::numeric
                      / NULLIF(SUM(quantity), 0)
            END                                         AS avg_price,
            MAX(subject_name)                           AS subject_name, -- просто способ добавить в результат доп информацию (бренд, артикул), можно было и через MIN
            MAX(brand_name)                             AS brand_name, 
            MAX(sa_name)                                AS sa_name

        FROM realization_report
        WHERE doc_type_name = 'Продажа'
          AND sale_dt IS NOT NULL
          AND nm_id > 0                       -- отсечь служебные записи WB
        GROUP BY nm_id, date_trunc('week', sale_dt)
        HAVING SUM(quantity) > 0              -- фильтр после группировки 
        ORDER BY nm_id, week
    """)
    return pd.read_sql(sql, ENGINE)


def get_weekly_stock() -> pd.DataFrame:
    """
    Недельные данные о наличии на уровне (nm_id, week).

    days_in_stock — сколько дней в неделе товар был хотя бы на одном складе
                    Главная фича для маскирования стокаутов.
    warehouses_with_stock — на скольких складах был товар (макс за неделю).
    """
    sql = text("""
        SELECT
            nm_id,
            date_trunc('week', date)::date            AS week,
            COUNT(DISTINCT date) FILTER (
                WHERE barcodes_count > 0
            )                                          AS days_in_stock,
            MAX(warehouses_per_day) FILTER (
                WHERE warehouses_per_day > 0
            )                                          AS warehouses_with_stock
        FROM (                                          -- вложенный цикл в запросе - сначала по дням, потом по неделям
            SELECT nm_id, date, 
                   COUNT(DISTINCT warehouse) FILTER (WHERE barcodes_count > 0)
                       AS warehouses_per_day,
                   SUM(barcodes_count) AS barcodes_count
            FROM paid_storage
            GROUP BY nm_id, date
        ) AS daily
        GROUP BY nm_id, date_trunc('week', date)
        ORDER BY nm_id, week
    """)
    return pd.read_sql(sql, ENGINE)


def get_full_weekly_panel() -> pd.DataFrame:
    """
    полная сетка (nm_id × week) от первой продажи каждого артикула
    до текущей недели. Нулевые недели заполнены явно (units=0)

    Колонки:
        nm_id, week, units, revenue_rub, avg_price,
        days_in_stock, warehouses_with_stock,
        subject_name, brand_name, sa_name
    """
    demand = get_weekly_demand()
    stock = get_weekly_stock()

    if demand.empty:
        return demand

    # текущая неделя (понедельник)
    today_week = pd.Timestamp.today().to_period("W-MON").start_time.date() # возвращает понедельник текущей недели

    panels = []
    for nm_id, group in demand.groupby("nm_id"):
        first_week = group["week"].min() # the earliest week where this ite, was sold 
        weeks = pd.date_range(first_week, today_week, freq="W-MON").date # the complete list of weeks
        meta = group[["subject_name", "brand_name", "sa_name"]].iloc[0].to_dict()
        panels.append(pd.DataFrame({
            "nm_id": nm_id,
            "week": weeks,
            **meta,
        }))
    panel = pd.concat(panels, ignore_index=True) # gluing data: panels on top of each other - we remove the initials indecies as well

    panel = panel.merge(
        demand[["nm_id", "week", "units", "revenue_rub", "avg_price"]],
        on=["nm_id", "week"], how="left"
    )
    panel = panel.merge(
        stock[["nm_id", "week", "days_in_stock", "warehouses_with_stock"]], # adding to the left - the missing data will be filled with NaaN
        on=["nm_id", "week"], how="left"
    )

    panel["units"] = panel["units"].fillna(0).astype(int) # NaaN are converted to 0, other data is int 
    panel["revenue_rub"] = panel["revenue_rub"].fillna(0).astype(float)
    panel["days_in_stock"] = panel["days_in_stock"].fillna(0).astype(int)
    panel["warehouses_with_stock"] = panel["warehouses_with_stock"].fillna(0).astype(int)

    return panel.sort_values(["nm_id", "week"]).reset_index(drop=True) # sort by item then by week - more readable. dropping indecies
