import json
import urllib.request
import urllib.error
import sys
import os

sys.path.insert(0, r"c:\Users\jerri\OneDrive\Desktop\farm\backend")
from app import issue_token, database_connection

BASE_URL = "http://127.0.0.1:8000"

def request(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def test_all():
    print("=== Testing E2E Features ===")

    # 1. Issue tokens for existing Farmer (user_id 1) and Officer (user_id 2)
    farmer_token = issue_token(1)
    officer_token = issue_token(2)
    print("[OK] Issued valid JWTs for Farmer (User #1) and Officer (User #2)")

    # 2. Test Master Reference Data (Crops must be Rice & Wheat)
    st, ref_data = request("GET", "/api/reference-data", token=farmer_token)
    assert st == 200, f"Get reference data failed: {ref_data}"
    crop_names = [c["crop_name"].lower() for c in ref_data["crops"]]
    assert "rice" in crop_names and "wheat" in crop_names, f"Rice & Wheat missing from crops: {crop_names}"
    print(f"[OK] Reference crops verified: {[c['crop_name'] for c in ref_data['crops']]}")

    # 3. Test Profile Edits
    # Farmer Profile Edit
    new_farmer_name = "Jerrin T Joby (Updated)"
    st, res = request("PUT", "/api/users/profile", {
        "full_name": new_farmer_name,
        "phone": "9847123999",
        "panchayath_id": 1,
        "address": "Green Fields, Alathur"
    }, token=farmer_token)
    assert st == 200, f"Farmer profile edit failed: {res}"
    assert res["user"]["full_name"] == new_farmer_name
    print("[OK] Farmer profile update verified.")

    # Officer Profile Edit
    new_officer_desig = "Senior Agricultural Officer"
    st, res = request("PUT", "/api/users/profile", {
        "full_name": "Suresh Kumar",
        "phone": "9847000111",
        "designation": new_officer_desig,
        "office_id": 1
    }, token=officer_token)
    assert st == 200, f"Officer profile edit failed: {res}"
    assert res["user"]["designation"] == new_officer_desig
    print("[OK] Officer profile update verified.")

    # 4. Get Farmer Overview
    st, overview = request("GET", "/api/farmer/overview", token=farmer_token)
    assert st == 200, f"Farmer overview failed: {overview}"
    farms = overview["farms"]
    crops = overview["crops"]
    assert len(farms) > 0, "Farmer should have at least one registered farm."
    farm = farms[0]
    print(f"[OK] Loaded farmer overview: {len(farms)} farms, {len(crops)} crops")

    # 5. Test Farm Edit
    updated_farm_name = f"Green Valley Plot #{farm['farm_id']}"
    st, res = request("PUT", "/api/farmer/farms", {
        "farm_id": farm["farm_id"],
        "farm_name": updated_farm_name,
        "location": farm["location"],
        "area_acres": float(farm["area_acres"]),
        "soil_type": "Clay Loam",
        "irrigation_type": "Canal Irrigation"
    }, token=farmer_token)
    assert st == 200, f"Farm edit failed: {res}"
    print("[OK] Farm edit verified.")

    # 6. Test Crop Variety Enforcement (Only Rice and Wheat allowed)
    if crops:
        crop = crops[0]
        # Attempt invalid crop edit if fake ID passed
        st, res = request("PUT", "/api/farmer/crops", {
            "farm_crop_id": crop["farm_crop_id"],
            "farm_id": farm["farm_id"],
            "crop_id": 9999,
            "season": "Kharif",
            "planting_date": "2026-06-01",
            "cultivated_area_acres": 2.5,
            "status": "GROWING"
        }, token=farmer_token)
        assert st == 400, f"Expected 400 for invalid crop ID, got {st}: {res}"
        print("[OK] Non-permitted crop rejected by backend.")

        # Valid crop edit (Rice or Wheat)
        st, res = request("PUT", "/api/farmer/crops", {
            "farm_crop_id": crop["farm_crop_id"],
            "farm_id": farm["farm_id"],
            "crop_id": 1, # Rice
            "season": "Kharif",
            "planting_date": "2026-06-01",
            "cultivated_area_acres": 2.5,
            "status": "GROWING"
        }, token=farmer_token)
        assert st == 200, f"Crop edit failed: {res}"
        print("[OK] Crop edit verified (Rice).")
    else:
        # Plant a crop
        st, res = request("POST", "/api/farmer/crops", {
            "farm_id": farm["farm_id"],
            "crop_id": 1,
            "season": "Kharif",
            "planting_date": "2026-06-01",
            "cultivated_area_acres": 2.0,
            "status": "GROWING"
        }, token=farmer_token)
        assert st == 201, f"Plant crop failed: {res}"
        st, overview = request("GET", "/api/farmer/overview", token=farmer_token)
        crop = overview["crops"][0]

    # 7. Test Expense, Income, Fertilizer, Labour Edits
    # Expense
    expenses = overview["expenses"]
    if expenses:
        exp = expenses[0]
        st, res = request("PUT", "/api/farmer/expenses", {
            "expense_id": exp["expense_id"],
            "farm_id": farm["farm_id"],
            "expense_category": exp["expense_category"],
            "amount": 1850.00,
            "expense_date": exp["expense_date"],
            "description": "Updated organic fertilizer expense"
        }, token=farmer_token)
        assert st == 200, f"Expense edit failed: {res}"
        print("[OK] Expense edit verified.")

    # Income
    income = overview["income"]
    if income:
        inc = income[0]
        st, res = request("PUT", "/api/farmer/income", {
            "income_id": inc["income_id"],
            "farm_crop_id": crop["farm_crop_id"],
            "sale_date": inc["sale_date"],
            "quantity_sold": 550.0,
            "unit": "kg",
            "price_per_unit": 29.50,
            "buyer_name": "SUPPLYCO Kerala"
        }, token=farmer_token)
        assert st == 200, f"Income edit failed: {res}"
        print("[OK] Income edit verified.")

    # Fertilizer
    fert = overview["fertilizers"]
    if fert:
        f = fert[0]
        st, res = request("PUT", "/api/farmer/fertilizers", {
            "application_id": f["application_id"],
            "farm_crop_id": crop["farm_crop_id"],
            "fertilizer_id": f["fertilizer_id"],
            "application_date": f["application_date"],
            "quantity": 45.0,
            "total_cost": 950.00
        }, token=farmer_token)
        assert st == 200, f"Fertilizer edit failed: {res}"
        print("[OK] Fertilizer edit verified.")

    # Labour
    labour = overview["labour"]
    if labour:
        l = labour[0]
        st, res = request("PUT", "/api/farmer/labour", {
            "labour_usage_id": l["labour_usage_id"],
            "farm_crop_id": crop["farm_crop_id"],
            "labour_id": l["labour_id"],
            "work_date": l["work_date"],
            "worker_count": 3,
            "days_worked": 2.0,
            "total_cost": 5100.00
        }, token=farmer_token)
        assert st == 200, f"Labour edit failed: {res}"
        print("[OK] Labour edit verified.")

    # 8. Test Subsidy Workflow: Application -> Pending (₹0) -> Edit -> Officer Review & Approval -> Disbursal
    subsidy_scheme = ref_data["subsidies"][0]
    st, apply_res = request("POST", "/api/farmer/subsidies", {
        "subsidy_id": subsidy_scheme["subsidy_id"],
        "application_date": "2026-10-12",
        "remarks": "Cultivating paddy across 2.5 acres, applying for seed subsidy."
    }, token=farmer_token)
    assert st in (200, 201), f"Apply subsidy failed: {apply_res}"
    print("[OK] Subsidy application submitted.")

    # Check farmer overview - pending subsidy must not be credited
    st, ov = request("GET", "/api/farmer/overview", token=farmer_token)
    subs = [s for s in ov["subsidies"] if s["subsidy_id"] == subsidy_scheme["subsidy_id"]]
    assert subs, "Submitted subsidy not found in overview"
    sub_record = subs[0]
    print(f"[OK] Subsidy #{sub_record['farmer_subsidy_id']} status is {sub_record['status']}.")

    # Reset status to PENDING in case it was already approved in previous run
    with database_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Farmer_Subsidies SET status = 'PENDING', approved_amount = NULL WHERE farmer_subsidy_id = %s", (sub_record["farmer_subsidy_id"],))
        conn.commit()
        cursor.close()

    # Re-verify pending status
    st, ov = request("GET", "/api/farmer/overview", token=farmer_token)
    sub_record = [s for s in ov["subsidies"] if s["farmer_subsidy_id"] == sub_record["farmer_subsidy_id"]][0]
    assert sub_record["status"] == "PENDING"
    assert sub_record["approved_amount"] is None

    # Farmer can edit pending subsidy
    st, edit_sub = request("PUT", "/api/farmer/subsidies", {
        "farmer_subsidy_id": sub_record["farmer_subsidy_id"],
        "subsidy_id": subsidy_scheme["subsidy_id"],
        "application_date": "2026-10-12",
        "remarks": "Updated land certificate attached, 2.5 acres."
    }, token=farmer_token)
    assert st == 200, f"Edit pending subsidy failed: {edit_sub}"
    print("[OK] Farmer successfully edited pending subsidy.")

    # Officer reviews and approves subsidy
    approved_grant = float(subsidy_scheme["amount"])
    st, rev = request("POST", "/api/officer/subsidies/review", {
        "farmer_subsidy_id": sub_record["farmer_subsidy_id"],
        "status": "APPROVED",
        "approved_amount": approved_grant,
        "remarks": "Field inspection verified by Krishi Bhavan officer."
    }, token=officer_token)
    assert st == 200, f"Officer review failed: {rev}"
    print(f"[OK] Officer approved subsidy for Rs.{approved_grant}.")

    # Farmer overview now reflects approved subsidy in stats
    st, ov_after = request("GET", "/api/farmer/overview", token=farmer_token)
    approved_sub = [s for s in ov_after["subsidies"] if s["farmer_subsidy_id"] == sub_record["farmer_subsidy_id"]][0]
    assert approved_sub["status"] == "APPROVED"
    assert float(approved_sub["approved_amount"]) == approved_grant
    assert float(ov_after["stats"]["approved_subsidies"]) >= approved_grant
    print("[OK] Approved subsidy reflected in farmer stats and credited to net balance.")

    # Farmer attempts to edit approved subsidy -> MUST BE REJECTED
    st, edit_rej = request("PUT", "/api/farmer/subsidies", {
        "farmer_subsidy_id": sub_record["farmer_subsidy_id"],
        "subsidy_id": subsidy_scheme["subsidy_id"],
        "application_date": "2026-10-12",
        "remarks": "Trying to modify approved grant."
    }, token=farmer_token)
    assert st == 400, f"Approved subsidy should not be editable, expected 400, got {st}"
    print("[OK] Editing approved subsidy properly rejected (policy enforced).")

    st, farmers_list = request("GET", "/api/officer/farmers", token=officer_token)
    assert st == 200, f"Officer get farmers failed: {farmers_list}"
    assert len(farmers_list["farmers"]) > 0, "Officer directory should contain farmers."
    target_farmer = farmers_list["farmers"][0]
    st, drilldown = request("GET", f"/api/officer/farmer-details?farmer_id={target_farmer['farmer_id']}", token=officer_token)
    assert st == 200, f"Officer drilldown failed: {drilldown}"
    assert "farms" in drilldown and "crops" in drilldown
    print(f"[OK] Officer directory drilldown displays details for farmer #{target_farmer['farmer_id']} ({target_farmer['farmer_name']}).")

    print("\nALL TESTS PASSED SUCCESSFULLY! DONE")

if __name__ == "__main__":
    test_all()
