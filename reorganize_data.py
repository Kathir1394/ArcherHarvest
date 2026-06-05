import os
import shutil
import asyncio
from pathlib import Path

from config import config
from instrument_loader import instrument_loader as loader

async def reorganize_data():
    data_dir = Path("dist/data")
    if not data_dir.exists():
        print("Data directory not found.")
        return

    print("Loading instruments...")
    await loader.load()
    
    unknown_dir = data_dir / "UNKNOWN_SEGMENT"
    if unknown_dir.exists():
        items_to_process = list(unknown_dir.iterdir())
    else:
        items_to_process = list(data_dir.iterdir())
        
    for item in items_to_process:
        if not item.is_dir():
            continue
            
        folder_name = item.name
        
        symbol = folder_name.replace("_", ":", 1)
        
        inst = loader.get_by_symbol(symbol)
        if inst:
            exchange = inst.get("exchange", "UNKNOWN")
            ui_segment = inst.get("ui_segment", "UNKNOWN").upper()
            if ui_segment == "EQUITY":
                target_category = f"{exchange} EQUITIES"
            elif ui_segment == "INDEX":
                target_category = "INDEX"
            elif ui_segment == "FUTURE":
                target_category = "FUTURES"
            elif ui_segment == "OPTION":
                target_category = "OPTIONS"
            elif ui_segment == "COMMODITY":
                target_category = "COMMODITIES"
            elif ui_segment == "ETF/MF":
                target_category = "ETF_MF"
            else:
                target_category = ui_segment
        else:
            target_category = "UNKNOWN_SEGMENT"
            
        target_dir = data_dir / target_category / folder_name
        
        if target_dir.exists() and str(item) != str(target_dir):
            print(f"Skipping {folder_name}, target already exists.")
            continue
            
        if target_category == "UNKNOWN_SEGMENT" and item.parent.name == "UNKNOWN_SEGMENT":
            continue
            
        (data_dir / target_category).mkdir(parents=True, exist_ok=True)
        print(f"Moving {folder_name} -> {target_category}/{folder_name}")
        shutil.move(str(item), str(target_dir))
        
    print("Reorganization complete.")

if __name__ == "__main__":
    asyncio.run(reorganize_data())
