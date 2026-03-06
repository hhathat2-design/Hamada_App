import io
import os
import zipfile
import tempfile
import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="hamada_App", layout="wide")

# ------------------ عنوان داخل إطار أخضر فاتح ------------------

st.markdown("""
<div style="
background-color:#e8f8ec;
padding:20px;
border-radius:12px;
border:2px solid #7bd389;
text-align:center;
margin-bottom:20px;
">
<h1 style="color:#1b5e20; margin:0;">
Web GIS for Spatial & Attribute Join
</h1>
</div>
""", unsafe_allow_html=True)

st.write("ارفع ملف Shapefile (ZIP) وملف GeoJSON لعرض الطبقات وتنفيذ عمليات الربط")

# --------------- Helpers ---------------------------------------------------------------------

def read_geojson(uploaded_file) -> gpd.GeoDataFrame:
    try:
        content = uploaded_file.read()
        uploaded_file.seek(0)
        return gpd.read_file(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"GeoJSON غير صالح أو لا يمكن قراءته. التفاصيل: {e}")

def read_shapefile_zip(uploaded_zip) -> gpd.GeoDataFrame:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "data.zip")
            with open(zip_path, "wb") as f:
                f.write(uploaded_zip.read())
            uploaded_zip.seek(0)

            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(tmpdir)

            shp_files = []
            for root, _, files in os.walk(tmpdir):
                for name in files:
                    if name.lower().endswith(".shp"):
                        shp_files.append(os.path.join(root, name))

            if not shp_files:
                raise ValueError("ملف zip لا يحتوي على ملف shp تأكد أنك رفعت Shapefile كامل مضغوط")

            shp_path = shp_files[0]
            gdf = gpd.read_file(shp_path)
            return gdf

    except zipfile.BadZipFile:
        raise ValueError("ملف zip تالف أو ليس بصيغة zip صحيحة")
    except Exception as e:
        raise ValueError(f"تعذر قراءة Shapefile من zip. التفاصيل: {e}")


def make_map(gdf: gpd.GeoDataFrame, name: str):
    if gdf is None or gdf.empty:
        st.warning(f" HT : {name}")
        return

    try:
        if gdf.crs is None:
            gdf_wgs = gdf
        else:
            gdf_wgs = gdf.to_crs(epsg=4326)
    except Exception:
        gdf_wgs = gdf

    center = [0, 0]
    try:
        c = gdf_wgs.geometry.unary_union.centroid
        center = [c.y, c.x]
    except Exception:
        pass

    m = folium.Map(location=center, zoom_start=6, control_scale=True)

    try:
        folium.GeoJson(
            data=gdf_wgs.__geo_interface__,
            name=name
        ).add_to(m)
        folium.LayerControl().add_to(m)
    except Exception as e:
        st.error(f"   Unable to display the map for  {name}. Details: {e}")
        return

    st_folium(m, height=320, width=None, key=f"map_{name}")

def preview_gdf(gdf: gpd.GeoDataFrame, n: int = 5):
    preview = gdf.head(n).copy()
    if "geometry" in preview.columns:
        preview["geometry"] = preview["geometry"].astype(str)
    return preview

# --------------- Sidebar ------------------------------------------------

with st.sidebar:
    st.header("  استلام الملفات")

    left_zip = st.file_uploader(
        " Shapefile ZIP",
        type=["zip"],
        accept_multiple_files=False
    )

    right_geojson = st.file_uploader(
        " GeoJSON",
        type=["geojson", "json"],
        accept_multiple_files=False
    )

    st.info("يتم رفع لان لكل ملف بشكل خاص وبعد ذلك سيعرض شكل الخرائط والجداول")

# ------------------------- Main layout ----------------------------------

col_left, col_right = st.columns(2)

if "left_gdf" not in st.session_state:
    st.session_state.left_gdf = None
if "right_gdf" not in st.session_state:
    st.session_state.right_gdf = None
if "join_result" not in st.session_state:
    st.session_state.join_result = None
if "attr_result" not in st.session_state:
    st.session_state.attr_result = None

# ------------------------------ Left -------------------------------------

with col_left:
    st.subheader("  Shapefile ZIP")
    if left_zip is not None:
        with st.spinner("جارٍ قراءة ملف الـ ZIP..."):
            try:
                st.session_state.left_gdf = read_shapefile_zip(left_zip)
                st.success(" تم تحميل ملف Left بنجاح")
            except ValueError as e:
                st.session_state.left_gdf = None
                st.error(str(e))

    if st.session_state.left_gdf is not None:
        make_map(st.session_state.left_gdf, "Left Layer")
        st.write("أول 5 صفوف:")
        st.dataframe(preview_gdf(st.session_state.left_gdf, 5))

# ------------------------------ Right ------------------------------------

with col_right:
    st.subheader(" GeoJSON")
    if right_geojson is not None:
        with st.spinner("جارٍ قراءة ملف GeoJSON..."):
            try:
                st.session_state.right_gdf = read_geojson(right_geojson)
                st.success(" تم تحميل ملف Right بنجاح")
            except ValueError as e:
                st.session_state.right_gdf = None
                st.error(str(e))

    if st.session_state.right_gdf is not None:
        make_map(st.session_state.right_gdf, "Right Layer")
        st.write("أول 5 صفوف:")
        st.dataframe(preview_gdf(st.session_state.right_gdf, 5))

# ================================================================================================
# Spatial Join
# ================================================================================================

st.divider()
st.header("ربط مكاني")

if st.session_state.left_gdf is None or st.session_state.right_gdf is None:
    st.warning(" ارفع ملفي و نفذ الربط المكاني")
else:
    with st.sidebar:
        st.header(" إعدادات Spatial Join")

        spatial_pred = st.selectbox(
            "اختر العلاقة المكانية:",
            options=["intersects", "contains", "within"],
            index=0
        )

        how_option = st.selectbox(
            "نوع الربط:",
            options=["left", "inner", "right"],
            index=0
        )

        run_spatial = st.button("تنفيذ")

    if run_spatial:
        with st.spinner("جاري التنفيذ"):
            try:
                left_gdf = st.session_state.left_gdf
                right_gdf = st.session_state.right_gdf

                if left_gdf.crs is not None and right_gdf.crs is not None:
                    if left_gdf.crs != right_gdf.crs:
                        right_gdf = right_gdf.to_crs(left_gdf.crs)

                try:
                    result = gpd.sjoin(
                        left_gdf,
                        right_gdf,
                        how=how_option,
                        predicate=spatial_pred,
                    )
                except TypeError:
                    result = gpd.sjoin(
                        left_gdf,
                        right_gdf,
                        how=how_option,
                        op=spatial_pred,
                    )

                st.session_state.join_result = result

                if result.empty:
                    st.warning(" لا توجد نتائج: لم يتم العثور على أي تطابق مكاني")
                else:
                    st.success(f" تم تنفيذ Spatial Join بنجاح عدد السجلات الناتجة: {len(result)}")
                    st.subheader(" معاينة النتائج (أول 10 صفوف)")
                    st.dataframe(preview_gdf(result, 10))

            except Exception as e:
                st.session_state.join_result = None
                st.error(f"حدث خطأ أثناء Spatial Join: {e}")

# ================================================================================================
# Attribute Join
# ================================================================================================

st.divider()
st.header("ربط وصفي")

if st.session_state.left_gdf is None or st.session_state.right_gdf is None:
    st.warning(" ارفع ملفي أولا ثم نفذ الربط الوصفي")
else:
    left_cols = [c for c in st.session_state.left_gdf.columns if c != "geometry"]
    right_cols = [c for c in st.session_state.right_gdf.columns if c != "geometry"]

    if len(left_cols) == 0 or len(right_cols) == 0:
        st.error("لا توجد أعمدة كافية للربط الوصفي (تحقق من الجداول)")
    else:
        with st.sidebar:
            st.header(" إعدادات Attribute Join")

            left_key = st.selectbox("اختر عمود الربط من Left:", options=left_cols)
            right_key = st.selectbox("اختر عمود الربط من Right:", options=right_cols)

            how_attr = st.selectbox(
                "نوع الربط:",
                options=["left", "inner", "right", "outer"],
                index=0
            )

            run_attr = st.button(" تنفيذ Attribute Join")

        if run_attr:
            with st.spinner("جارٍ تنفيذ Attribute Join..."):
                try:
                    left_gdf = st.session_state.left_gdf.copy()
                    right_df = st.session_state.right_gdf.copy()

                    if "geometry" in right_df.columns:
                        right_df = right_df.drop(columns=["geometry"])

                    left_gdf[left_key] = left_gdf[left_key].astype(str)
                    right_df[right_key] = right_df[right_key].astype(str)

                    result_attr = left_gdf.merge(
                        right_df,
                        how=how_attr,
                        left_on=left_key,
                        right_on=right_key,
                        suffixes=("_L", "_R")
                    )

                    st.session_state.attr_result = result_attr

                    if result_attr.empty:
                        st.warning(" لا توجد نتائج: لم يتم العثور على أي تطابق وصفي")
                    else:
                        st.success(f" تم تنفيذ Attribute Join بنجاح. عدد السجلات الناتجة: {len(result_attr)}")
                        st.subheader(" معاينة النتائج (أول 10 صفوف)")
                        st.dataframe(preview_gdf(result_attr, 10))

                except Exception as e:
                    st.session_state.attr_result = None
                    st.error(f"حدث خطأ أثناء Attribute Join: {e}")

# ================================================================================================
# Download Result
# ================================================================================================

st.divider()
st.header(" تنزيل النتيجة")

final_result = None
final_name = None

if st.session_state.attr_result is not None:
    final_result = st.session_state.attr_result
    final_name = "attribute_join_result.geojson"
elif st.session_state.join_result is not None:
    final_result = st.session_state.join_result
    final_name = "spatial_join_result.geojson"

if final_result is None:
    st.info(" Spatial Join أو Attribute Join   إمكانية التنزيل")
else:
    if final_result.empty:
        st.info("لا يوجد ملف لتنزيله لأن النتيجة فارغة.")
    else:
        try:
            geojson_bytes = final_result.to_json().encode("utf-8")
            st.download_button(
                label=" تنزيل النتيجة GeoJSON",
                data=geojson_bytes,
                file_name=final_name,
                mime="application/geo+json"
            )
        except Exception as e:
            st.error(f"تعذر تجهيز ملف GeoJSON للتنزيل: {e}")