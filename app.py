import streamlit as st
import pandas as pd

from data_quality_checker import load_dataset, run_quality_checks_on_df


st.set_page_config(
    page_title="AI Data Quality Assistant",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 AI Data Quality Assistant")
st.write(
    "Upload an Excel or CSV file to detect possible data-quality issues. "
    "The tool reviews the data and creates a report; it does not modify your original file."
)

uploaded_file = st.file_uploader(
    "Choose a CSV or Excel file",
    type=["csv", "xlsx", "xls"],
)

if uploaded_file is not None:
    try:
        df = load_dataset(uploaded_file)
        if df.empty:
            st.warning("The uploaded file has no data rows.")
            st.stop()

        report = run_quality_checks_on_df(df)

        st.subheader("Dataset overview")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows", f"{len(df):,}")
        c2.metric("Columns", f"{len(df.columns):,}")
        c3.metric("Issues found", f"{len(report):,}")

        with st.expander("Preview uploaded data", expanded=True):
            st.dataframe(df.head(20), use_container_width=True)

        st.subheader("Quality report")
        if report.empty:
            st.success("No issues were detected by the current checks.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("High severity", int((report["severity"] == "High").sum()))
            m2.metric("Needs review", int((report["severity"] == "Review").sum()))
            m3.metric("Medium / Low", int(report["severity"].isin(["Medium", "Low"]).sum()))

            severity_filter = st.multiselect(
                "Filter by severity",
                options=["High", "Review", "Medium", "Low"],
                default=["High", "Review", "Medium", "Low"],
            )
            filtered = report[report["severity"].isin(severity_filter)]
            st.dataframe(filtered, use_container_width=True, hide_index=True)

            csv_bytes = report.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Download full quality report (CSV)",
                data=csv_bytes,
                file_name="data_quality_report.csv",
                mime="text/csv",
            )

        st.caption(
            "Important: flags are prompts for human review, not proof of errors. "
            "For example, negative quantities may represent returns and outliers may be valid."
        )

    except Exception as exc:
        st.error(f"Could not read or analyze this file: {exc}")
        st.info("Check that the file is a valid CSV or Excel workbook and try again.")
else:
    st.info("Upload a file to begin. You can test the app with your sample CSV.")
