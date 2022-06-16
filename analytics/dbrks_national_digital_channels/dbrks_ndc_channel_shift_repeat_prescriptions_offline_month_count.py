# Databricks notebook source
#!/usr/bin python3

# -------------------------------------------------------------------------
# Copyright (c) 2021 NHS England and NHS Improvement. All rights reserved.
# Licensed under the MIT License. See license.txt in the project root for
# license information.
# -------------------------------------------------------------------------

"""
FILE:           dbrks_ndc_channel_shift_repeat_prescriptions_offline_month_count.py
DESCRIPTION:
                Databricks notebook with processing code for the NHSX Analyticus unit metric M250: Repeat prescriptions offline
USAGE:
                ...
CONTRIBUTORS:   Mattia Ficarelli
CONTACT:        data@nhsx.nhs.uk
CREATED:        16th June 2022
VERSION:        0.0.1
"""

# COMMAND ----------

# Install libs
# -------------------------------------------------------------------------
%pip install geojson==2.5.* tabulate requests pandas pathlib azure-storage-file-datalake beautifulsoup4 numpy urllib3 lxml regex pyarrow==5.0.*

# COMMAND ----------

# Imports
# -------------------------------------------------------------------------
# Python:
import os
import io
import tempfile
from datetime import datetime
import json

# 3rd party:
import pandas as pd
import numpy as np
from pathlib import Path
from azure.storage.filedatalake import DataLakeServiceClient

# Connect to Azure datalake
# -------------------------------------------------------------------------
# !env from databricks secrets
CONNECTION_STRING = dbutils.secrets.get(scope="datalakefs", key="CONNECTION_STRING")

# COMMAND ----------

# MAGIC %run /Repos/prod/au-azure-databricks/functions/dbrks_helper_functions

# COMMAND ----------

#Download JSON config from Azure datalake
file_path_config = "/config/pipelines/nhsx-au-analytics/"
file_name_config = "config_national_digital_channels_dbrks.json"
file_system_config = "nhsxdatalakesagen2fsprod"
config_JSON = datalake_download(CONNECTION_STRING, file_system_config, file_path_config, file_name_config)
config_JSON = json.loads(io.BytesIO(config_JSON).read())

# COMMAND ----------

#Get parameters from JSON config
file_system = config_JSON['pipeline']['adl_file_system']
source_path = config_JSON['pipeline']['project']['source_path']
source_file = config_JSON['pipeline']['project']["source_file_daily"]
reference_source_path = config_JSON['pipeline']['project']["reference_source_path_pomi"]
reference_source_file = config_JSON['pipeline']['project']["reference_source_file_pomi"]
sink_path = config_JSON['pipeline']['project']['databricks'][37]['sink_path']
sink_file = config_JSON['pipeline']['project']['databricks'][37]['sink_file']  

# COMMAND ----------

# Ingestion of numerator data
# ---------------------------------------------------------------------------------------------------
latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, source_path)
file = datalake_download(CONNECTION_STRING, file_system, source_path+latestFolder, source_file)
df = pd.read_parquet(io.BytesIO(file), engine="pyarrow")

# Ingestion of POMI data
# ---------------------------------------------------------------------------------------------------
ref_latestFolder = datalake_latestFolder(CONNECTION_STRING, file_system, reference_source_path)
file = datalake_download(CONNECTION_STRING, file_system, reference_source_path+ref_latestFolder, reference_source_file)
df_ref = pd.read_parquet(io.BytesIO(file), engine="pyarrow")

# COMMAND ----------

#Processing
# ---------------------------------------------------------------------------------------------------

#Numerator
# ---------------------------------------------------------------------------------------------------
df_1 = df[["Daily", "eps_repeat_prescriptions"]]
df_1.iloc[:, 0] = df_1.iloc[:,0].dt.strftime('%Y-%m')
df_2 = df_1.groupby(df_1.iloc[:,0]).sum().reset_index()
df_2.rename(columns  = {'Daily': 'Date', "eps_repeat_prescriptions": "Number of EPS repeat prescriptions"}, inplace = True)

#Denominator porcessing
# ---------------------------------------------------------------------------------------------------
df_ref_1 = df_ref[["Report_Period_End", "Field", "Value"]]
df_ref_2 = df_ref_1[df_ref_1['Field']=='Pat_Presc_Use'].reset_index(drop = True)
df_ref_2["Report_Period_End"] = pd.to_datetime(df_ref_2["Report_Period_End"]).dt.strftime('%Y-%m')
df_ref_3 = df_ref_2.groupby('Report_Period_End')['Value'].sum().reset_index()

# COMMAND ----------

#Joint processing 
# ---------------------------------------------------------------------------------------------------
df_joint = df_2.merge(df_ref_3, how = 'inner', left_on = 'Date', right_on = 'Report_Period_End')
df_joint_1 = df_joint.drop(columns = ['Report_Period_End'])
df_joint_1.rename(columns = {'Value': 'Total number of online repeat prescriptions'}, inplace=True)
df_joint_1['Number of offline repeat prescriptions'] = df_joint_1['Number of EPS repeat prescriptions'] - df_joint_1['Total number of online repeat prescriptions'] 
df_joint_1 = df_joint_1[df_joint_1['Number of offline repeat prescriptions'] > 0].reset_index(drop = True)
df_joint_1.index.name = "Unique ID"
df_joint_2 = df_joint_1.round(4)
df_processed = df_joint_2.copy()

# COMMAND ----------

#Upload processed data to datalake
file_contents = io.StringIO()
df_processed.to_csv(file_contents)
datalake_upload(file_contents, CONNECTION_STRING, file_system, sink_path+latestFolder, sink_file)
