import os
import math
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))


def load_warehouses(data: List[Dict]) -> int:
    df = pd.DataFrame(data)
    df = df.rename(columns={
        "ID":              "id",
        "name":            "name",
        "address":         "address",
        "workTime":        "work_time",
        "isActive":        "is_active",
        "isTransitActive": "is_transit_active",
    })
    df.to_sql("warehouses", engine, if_exists="replace", index=False)
    return len(df)


def load_warehouse_remains(data: List[Dict]) -> int: 
    df = pd.json_normalize(data, record_path="warehouses", meta=["nmId", "volume"]) # meta allows to glue the listed objects to each row
    df = df.rename(columns={
        "nmId":          "nm_id",
        "volume":        "volume",
        "warehouseName": "warehouse_name",
        "quantity":      "quantity",
    })
    df = df[["nm_id", "volume", "warehouse_name", "quantity"]]
    df.to_sql("warehouse_remains", engine, if_exists="replace", index=False)
    return len(df)


def load_paid_storage(data: List[Dict]) -> int:
    df = pd.DataFrame(data)
    df = df.rename(columns={
        "date":             "date",
        "nmId":             "nm_id",
        "chrtId":           "chrt_id",
        "giId":             "gi_id",
        "barcode":          "barcode",
        "warehouse":        "warehouse",
        "officeId":         "office_id",
        "warehouseCoef":    "warehouse_coef",
        "logWarehouseCoef": "log_warehouse_coef",
        "size":             "size",
        "subject":          "subject",
        "brand":            "brand",
        "vendorCode":       "vendor_code",
        "volume":           "volume",
        "calcType":         "calc_type",
        "warehousePrice":   "warehouse_price",
        "barcodesCount":    "barcodes_count",
        "palletPlaceCode":  "pallet_place_code",
        "palletCount":      "pallet_count",
        "originalDate":     "original_date",
        "loyaltyDiscount":  "loyalty_discount",
        "tariffFixDate":    "tariff_fix_date",
        "tariffLowerDate":  "tariff_lower_date",
    })
  
    for col in ["tariff_fix_date", "tariff_lower_date", "original_date"]:
        df[col] = df[col].replace("", None)

    cols = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])
    sql = text(f"INSERT INTO paid_storage ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING") # SQLAlchemy запрос 
    records = df.to_dict(orient="records") # each row is a dict 
    for record in records:
        for k, v in record.items():
            if isinstance(v, float) and math.isnan(v):
                record[k] = None # NaaN -> None -> sql treats None as NULL
    with engine.begin() as conn:
        conn.execute(sql, records) # bulk insert 
    return len(df)


def load_region_sale(data: List[Dict]) -> int:
    df = pd.DataFrame(data)
    df = df.rename(columns={
        "nmID":                     "nm_id",
        "sa":                       "sa",
        "cityName":                 "city_name",
        "regionName":               "region_name",
        "countryName":              "country_name",
        "foName":                   "fo_name",
        "saleInvoiceCostPrice":     "sale_invoice_cost_price",
        "saleInvoiceCostPricePerc": "sale_invoice_cost_price_perc",
        "saleItemInvoiceQty":       "sale_item_invoice_qty",
    })
    df.to_sql("region_sale", engine, if_exists="append", index=False)
    return len(df)


def load_goods_return(data: List[Dict]) -> int:
    df = pd.DataFrame(data)
    if df.empty:
        return 0
    df = df.rename(columns={
        "srid":              "srid",
        "orderID":           "order_id",
        "nmID":              "nm_id",
        "barcode":           "barcode",
        "brand":             "brand",
        "subjectName":       "subject_name",
        "techSize":          "tech_size",
        "shkID":             "shk_id",
        "stickerID":         "sticker_id",
        "orderDt":           "order_dt",
        "expiredDt":         "expired_dt",
        "readyToReturnDt":   "ready_to_return_dt",
        "completedDt":       "completed_dt",
        "returnType":        "return_type",
        "reason":            "reason",
        "status":            "status",
        "isStatusActive":    "is_status_active",
        "dstOfficeID":       "dst_office_id",
        "dstOfficeAddress":  "dst_office_address",
    })
    keep = [c for c in [
        "srid","order_id","nm_id","barcode","brand","subject_name","tech_size",
        "shk_id","sticker_id","order_dt","expired_dt","ready_to_return_dt",
        "completed_dt","return_type","reason","status","is_status_active",
        "dst_office_id","dst_office_address"
    ] if c in df.columns]
    df = df[keep].copy()

    
    for col in ["order_dt", "expired_dt", "ready_to_return_dt", "completed_dt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce") # if we cannot convert to datetime, we convert to NaT -> None


    if "is_status_active" in df.columns:
        df["is_status_active"] = df["is_status_active"].apply(
            lambda x: bool(x) if pd.notna(x) else None
        )

    cols = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])
    sql = text(f"INSERT INTO goods_return ({cols}) VALUES ({placeholders}) ON CONFLICT (srid) DO NOTHING")

    records = df.to_dict(orient="records")
    for record in records:
        for k, v in record.items():
            if v is pd.NaT or (isinstance(v, float) and math.isnan(v)):
                record[k] = None

    with engine.begin() as conn:
        conn.execute(sql, records)
    return len(df)


def _load_statistics_table(data: List[Dict], table: str, pk: str, mapping: Dict[str, str],
                           date_cols: List[str], bool_cols: List[str]) -> int:
    df = pd.DataFrame(data)
    if df.empty:
        return 0

    df = df.rename(columns=mapping)
    keep = [c for c in mapping.values() if c in df.columns]
    df = df[keep].copy()

    # remove dublicates using and keep the last version
    df = df.drop_duplicates(subset=[pk], keep="last")

    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(bool)

    cols = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])
    sql = text(f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT ({pk}) DO NOTHING")
    records = df.to_dict(orient="records")
    for record in records:
        for k, v in record.items():
            if v is pd.NaT or (isinstance(v, float) and math.isnan(v)):
                record[k] = None
    with engine.begin() as conn:
        conn.execute(sql, records)
    return len(df)


SALES_MAPPING = {
    "saleID":           "sale_id",
    "date":             "date",
    "lastChangeDate":   "last_change_date",
    "nmId":             "nm_id",
    "supplierArticle":  "supplier_article",
    "barcode":          "barcode",
    "techSize":         "tech_size",
    "category":         "category",
    "subject":          "subject",
    "brand":            "brand",
    "warehouseName":    "warehouse_name",
    "countryName":      "country_name",
    "regionName":       "region_name",
    "totalPrice":       "total_price",
    "discountPercent":  "discount_percent",
    "spp":              "spp",
    "priceWithDisc":    "price_with_disc",
    "forPay":           "for_pay",
    "finishedPrice":    "finished_price",
    "isCancel":         "is_cancel",
    "orderType":        "order_type",
    "sticker":          "sticker",
    "gNumber":          "g_number",
    "srid":             "srid",
}

ORDERS_MAPPING = {
    "srid":             "srid",
    "date":             "date",
    "lastChangeDate":   "last_change_date",
    "nmId":             "nm_id",
    "supplierArticle":  "supplier_article",
    "barcode":          "barcode",
    "techSize":         "tech_size",
    "category":         "category",
    "subject":          "subject",
    "brand":            "brand",
    "warehouseName":    "warehouse_name",
    "countryName":      "country_name",
    "regionName":       "region_name",
    "totalPrice":       "total_price",
    "discountPercent":  "discount_percent",
    "spp":              "spp",
    "priceWithDisc":    "price_with_disc",
    "finishedPrice":    "finished_price",
    "isCancel":         "is_cancel",
    "cancelDate":       "cancel_date",
    "orderType":        "order_type",
    "sticker":          "sticker",
    "gNumber":          "g_number",
}


def load_realization_report(data: List[Dict]) -> int:
    df = pd.DataFrame(data)
    if df.empty:
        return 0
    df = df.rename(columns={
        "rrd_id":                    "rrd_id",
        "date_from":                 "date_from",
        "date_to":                   "date_to",
        "nm_id":                     "nm_id",
        "sa_name":                   "sa_name",
        "ts_name":                   "ts_name",
        "barcode":                   "barcode",
        "subject_name":              "subject_name",
        "brand_name":                "brand_name",
        "doc_type_name":             "doc_type_name",
        "quantity":                  "quantity",
        "retail_price":              "retail_price",
        "retail_price_withdisc_rub": "retail_price_withdisc_rub",
        "ppvz_for_pay":              "ppvz_for_pay",
        "sale_percent":              "sale_percent",
        "commission_percent":        "commission_percent",
        "office_name":               "office_name",
        "supplier_oper_name":        "supplier_oper_name",
        "order_dt":                  "order_dt",
        "sale_dt":                   "sale_dt",
        "penalty":                   "penalty",
        "additional_payment":        "additional_payment",
        "srid":                      "srid",
    })
    keep = [c for c in [
        "rrd_id", "date_from", "date_to", "nm_id", "sa_name", "ts_name",
        "barcode", "subject_name", "brand_name", "doc_type_name", "quantity",
        "retail_price", "retail_price_withdisc_rub", "ppvz_for_pay",
        "sale_percent", "commission_percent", "office_name", "supplier_oper_name",
        "order_dt", "sale_dt", "penalty", "additional_payment", "srid",
    ] if c in df.columns]
    df = df[keep].copy()
    for col in ["order_dt", "sale_dt", "date_from", "date_to"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            
    cols = ", ".join(df.columns)
    placeholders = ", ".join([f":{c}" for c in df.columns])
    sql = text(f"INSERT INTO realization_report ({cols}) VALUES ({placeholders}) ON CONFLICT (rrd_id) DO NOTHING")
    records = df.to_dict(orient="records")
    for record in records:
        for k, v in record.items():
            if v is pd.NaT or (isinstance(v, float) and math.isnan(v)):
                record[k] = None
    with engine.begin() as conn:
        conn.execute(sql, records)
    return len(df)


def load_supplier_sales(data: List[Dict]) -> int:
    return _load_statistics_table(
        data, "supplier_sales", "sale_id", SALES_MAPPING,
        date_cols=["date", "last_change_date"],
        bool_cols=["is_cancel"],
    )


def load_supplier_orders(data: List[Dict]) -> int:
    return _load_statistics_table(
        data, "supplier_orders", "srid", ORDERS_MAPPING,
        date_cols=["date", "last_change_date", "cancel_date"],
        bool_cols=["is_cancel"],
    )
