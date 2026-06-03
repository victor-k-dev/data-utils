# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# TODO: Make import/export functions methods of CSVData
#		Rename variables for clarity
#		Finish splitting logic in import_csv()
#		Implement row and column metadata objects in analyze_data_from_csv() and other functions
#		Store modified csv row data separately from row metadata
#		Determine more robust way to detect unix timestamps in analyze_data_from_csv()
#		Consider making object for column/type mappings
#		Finish documentation for functions
#		remove_duplicate_columns contains hardcoded column names
#		add_rows contains hardcoded column names and other values
#		date_range parameter in add_rows should be a DatetimeIndex
#		Choose a more descriptive name for add_rows
#		Add parameters for determing fill method to add_rows
#		consider moving analysis and cleaning functions to their own modules
#		General readability improvements (follow PEP guidelines?)

import csv
import pandas as pd
import re
from copy import deepcopy
from datetime import datetime, timezone
from dateutil import parser
from dateutil.parser import ParserError
from decimal import Decimal
from io import StringIO

# Typing
from typing import Any, Literal
from pandas import DataFrame


#class RowMetadata():
#	def __init__(self, file_name:str, row_metadata):
#		self.file_name = file_name
#		self.row_metadata = row_metadata
#
#class ColumnMetadata():
#	def __init__(self, file_name:str, column_metadata):
#		self.file_name = file_name
#		self.column_metadata = column_metadata
#
#class CSVMetadata():
#	def __init__(self):
#		pass
		
class CSVData():
	def __init__(self, name:str, headers:list[str], data:dict[str,list[str]]|list[dict[str,list[str]]], file_names:set[str]|None=None):
		self.name = name
		self.file_names = None
		self.file_count = 0
		self.headers = headers
		self.file_data = self.init_file_data(data, file_names)
		self.row_metadata = None
		self.column_metadata = None
		self.dtype_mappings = None
		self.dataframes = {}

	def init_file_data(self, imported_data:dict[str,dict], file_names:set[str]=None) -> dict[str,Any]|dict[str,dict[str,Any]]|None:
		if not file_names:
			if isinstance(imported_data, dict):
				self.file_count = 1
				return imported_data
			else:
				raise ValueError("received file data of type %s, expected %s" % (type(imported_data), type(dict())))
		else:
			if len(file_names) != len(imported_data):
				raise ValueError("count of file data (%s) and file names (%s) are not the same" % (len(imported_data), len(file_names)))
			self.file_names = [name for name in file_names]
			file_data = {}
			for file_name in self.file_names:
				if isinstance(imported_data[file_name], dict):		
					file_data[file_name] = imported_data[file_name]
					self.file_count += 1
				else:
					raise ValueError("received file data of type %s, expected %s" % (type(imported_data), type(dict())))
			return file_data
	
	def set_row_metadata(self, row_metadata, file_name:str|None=None) -> None:
		if not self.row_metadata:
			if self.file_count == 1:
				self.row_metadata = deepcopy(row_metadata)
			else:
				self.row_metadata = {}
				self.row_metadata[file_name] = deepcopy(row_metadata)
		else:
			if self.file_count > 1:
				#print("%s:row:new" % file_name, sha256(pickle.dumps(row_metadata)).hexdigest())
				#if file_name in self.row_metadata:
				#	print("%s:row:before" % file_name, sha256(pickle.dumps(self.row_metadata[file_name])).hexdigest())
				self.row_metadata[file_name] = deepcopy(row_metadata)
				#if file_name in self.row_metadata:
				#	print("%s:row:after" % file_name, sha256(pickle.dumps(self.row_metadata[file_name])).hexdigest())
			else:
				self.row_metadata[file_name] = deepcopy(row_metadata)
	
	def set_column_metadata(self, column_metadata, file_name:str|None=None) -> None:
		if not self.column_metadata:
			if self.file_count == 1:
				self.column_metadata = deepcopy(column_metadata)
			elif self.file_count > 1:
				self.column_metadata = {}
				self.column_metadata[file_name] = deepcopy(column_metadata)
		else:
			if self.file_count == 1:
				self.column_metadata = deepcopy(column_metadata)
			elif self.file_count > 1:
				#print("%s:column:new" % file_name, sha256(pickle.dumps(column_metadata)).hexdigest())
				#if file_name in self.column_metadata:
				#	print("%s:column:before" % file_name, sha256(pickle.dumps(self.column_metadata[file_name])).hexdigest())
				self.column_metadata[file_name] = deepcopy(column_metadata)
				#if file_name in self.column_metadata:
				#	print("%s:column:after" % file_name, sha256(pickle.dumps(self.column_metadata[file_name])).hexdigest())

	def set_dtype_mappings(self, mappings, file_name:str|None=None):
		if not self.dtype_mappings:
			if self.file_count == 1:
				self.dtype_mappings = deepcopy(mappings)
			elif self.file_count > 1:
				self.dtype_mappings = {}
				self.dtype_mappings[file_name] = deepcopy(mappings)
		else:
			if self.file_count == 1:
				self.dtype_mappings = deepcopy(mappings)
			elif self.file_count > 1:
				self.dtype_mappings[file_name] = deepcopy(mappings)
				
	def set_name(self, name:str) -> None:
		self.name = name
	def get_file_names(self) -> set[str]|None:
		return self.file_names
	
	

def csv_has_headers(file_name) -> bool:
	with open(file_name, "r", newline="") as f:
		sniffer = csv.Sniffer()
		has_header = sniffer.has_header(f.read(16384))
		return has_header

def import_csv(file_name:str, split_by:Literal["column", "row"]|None=None, column:str|None=None, row:int|None=None, split_value:str|None=None) -> CSVData:
	"""
		Import a CSV file and optionally split it row-wise by unique column values or row index.

		Parameters
		----------
			file_name: str
				The name/path of the CSV file to import
			split_by: Literal["column", "row"] | None
				Whether to split the CSV file by column value or row index. Optional.
			column: str | None
				Name of the column to use for splitting by unique values. Optional unless `split_by` is set.
			row: int | None
				Row index to split by. Optional unless `split_by` is set.
			split_value: str | None
				Currently unused
		Returns
		-------
			CSVData
		Notes
		-----
			Splitting by row index or specified value is currently not implemented, and will raise `NotImplementedError`

	"""
	with open(file_name, "r", newline="") as f:
		rows = f.readlines()

		if csv_has_headers(file_name):
			headers = [header.strip() for header in rows[0].split(",")]
		else:
			headers = [f"col{i}" for i in range(0, len(rows[0].split(",")))]
		
		raw_data:dict[str,list[str]] = {header: [] for header in headers}
		for i in range(1, len(rows)):
			row_vals = rows[i].split(",")
			for header, row_val in zip(headers, row_vals):
				raw_data[header].append(row_val.strip())

		if split_by == "column":
			split_data = {}
			data = {header: [] for header in headers}
			unique_values = set()
			current_value = None
			if column in headers:
				current_value = raw_data[column][0]
				for i in range(0, len(raw_data[column])):
					if raw_data[column][i] == current_value or "":
						for header in headers:
							data[header].append(raw_data[header][i])
					elif raw_data[column][i] != current_value or "":
						unique_values.add(current_value)
						split_data[current_value] = deepcopy(data)
						current_value = raw_data[column][i]
						
						data.clear()
						data = {header: [] for header in headers}
						for header in headers:
							data[header].append(raw_data[header][i])
				else:
					if data and current_value not in unique_values:
						split_data[current_value] = deepcopy(data)
						unique_values.add(current_value)

				split_csv_files = CSVData("split_csv", headers, split_data, unique_values)
				return split_csv_files
			else:
				raise ValueError("column name '%s' not found in CSV file" % column)
		elif split_by == "row":
			raise NotImplementedError("only splitting csv data by unique column values is currently supported")
		else:
			raw_csv_data = CSVData("raw_csv",headers, raw_data)
			return raw_csv_data

def export_to_csv(file_name, row_metadata:dict[str,dict], headers:list[str]) -> None:
	"""
		Extracts the CSV row data from the row metadata and exports it to a CSV file.

		Parameters
		----------
			file_name: str
				The name of the output file
			row_metadata: dict[str,dict[str,Any]]
				Contains the row data and metadata for a CSV file
			headers: list[str]
				The column names from the CSV file
		Returns
		-------
			None
	"""
	with open(file_name, "w") as f:
		f.write(",".join(headers))
		f.write("\n")

		for i in range(0, len(row_metadata[headers[0]])):
			line = ""
			for header in headers:
				line = line + row_metadata[header][i]["value"] + ","
			line = line.removesuffix(",")
			f.write(line)
			f.write("\n")

def export_to_buffer(row_metadata:dict[str,dict], headers:list[str]) -> StringIO:
	"""
		Extracts the CSV row data from the row metadata and exports it to a StringIO buffer.
		This buffer is compatible with `pandas.read_csv()`.

		Parameters
		----------
			row_metadata: dict[str,dict[str,Any]]
				Contains the row data and metadata for a CSV file
			headers: list[str]
				The column names from the CSV file
		Returns
		-------
			StringIO
	"""

	output = StringIO()
	output.write(",".join(headers))
	output.write("\n")

	for i in range(0, len(row_metadata[headers[0]])):
		line = ""
		for header in headers:
			line = line + row_metadata[header][i]["value"] + ","
		line = line.removesuffix(",")
		output.write(line)
		output.write("\n")
	
	output.seek(0)
	return output

def analyze_data_from_csv(csv_data:dict[str,list[str]], headers:list[str]) -> tuple[dict[str, dict], dict[str, dict[str, Any]]]:
	"""
		Analyze an imported CSV file, and return metadata for both columns and individual rows.

		Parameters
		----------
			csv_data: dict[str,list[str]]
				Imported data from the CSV file
			headers: list[str]
				Column names extracted from the CSV File
		Returns
		-------
			tuple[dict[str, dict], dict[str, dict[str, Any]]]
		Raises
		------
			RuntimeError
				If the majority data type for a column cannot be determined
		Notes
		-----
			Will not attempted to determine whether integer values are unix timestamps
	"""
	row_metadata = {header: {} for header in headers}
	column_metadata = {header: {
		"integer_count": 0, 
		"float_count": 0, 
		"decimal_count": 0, 
		"boolean_count": 0,
		"date_count": 0,
		"timestamp_count": 0,
		"string_count": 0,
		"null_count": 0,
		"unique_values": set({}),
		"unique_value_count": 0,
		"item_count": 0,
		"is_category": False,
		"mixed_dtypes": False,
		"has_null_values": False,
		"majority_type": None,
		} for header in headers}
	
	for header in headers:
		index = 0
		for value in csv_data[header]:
			row_metadata[header][index] = {
				"value": value, 
				"is_integer": value.isnumeric() or True if value.removeprefix("-").isnumeric() else False, 
				"is_float": True if re.compile(r"^(?:-|)\d+\.\d+$").match(value) else False,
				"is_fixed_precision": False,
				"is_boolean": True if re.compile(r"^(?:true|false)$").match(value.lower()) else False,
				"is_date": False,
				"is_timestamp": False,
				"is_category": False,
				"is_string": False,
				"is_null": True if not value else False
			}
			
			if row_metadata[header][index]["is_float"]:
				left_digits, right_digits = value.split(".")
				row_metadata[header][index]["is_fixed_precision"] = True if right_digits[-1] == "0" else False
				# TODO: set 'is_float' to false if 'is_fixed_precision' is true?

			#if row_metadata[header][index]["is_integer"]:
			#	digit_count = len(value)
			#	if digit_count in [10,13,16,19]:
			#		ts_precision = INVERSE_UNIX_TIMESTAMP_PRECISION[digit_count]
			#		current_time = datetime.now(tz=timezone.utc)
			#		ts_chars = list(value)
			#		ts_chars.insert(10, ".")
			#		ts_float = float("".join(ts_chars))
			#		if current_time > datetime.fromtimestamp(ts_float, tz=timezone.utc):
			#			row_metadata[header][index]["is_timestamp"] = True
			#			row_metadata[header][index]["is_integer"] = False

			column_metadata[header]["integer_count"] = column_metadata[header]["integer_count"] + 1 if row_metadata[header][index]["is_integer"] else column_metadata[header]["integer_count"]
			column_metadata[header]["float_count"] = column_metadata[header]["float_count"] + 1 if row_metadata[header][index]["is_float"] and not row_metadata[header][index]["is_fixed_precision"] else column_metadata[header]["float_count"]
			column_metadata[header]["decimal_count"] = column_metadata[header]["decimal_count"] + 1 if row_metadata[header][index]["is_fixed_precision"] else column_metadata[header]["decimal_count"]
			column_metadata[header]["boolean_count"] = column_metadata[header]["boolean_count"] + 1 if row_metadata[header][index]["is_boolean"] else column_metadata[header]["boolean_count"]
			column_metadata[header]["timestamp_count"] = column_metadata[header]["timestamp_count"] + 1 if row_metadata[header][index]["is_timestamp"] else column_metadata[header]["timestamp_count"]
			column_metadata[header]["null_count"] = column_metadata[header]["null_count"] + 1 if row_metadata[header][index]["is_null"] else column_metadata[header]["null_count"]
			if value:
				column_metadata[header]["unique_values"].add(value) 
			
			index += 1
			column_metadata[header]["item_count"] += 1

	for header in headers:
		column_metadata[header]["unique_value_count"] = len(column_metadata[header]["unique_values"])
		
		if column_metadata[header]["null_count"] > 0:
			column_metadata[header]["has_null_values"] = True

		if len(column_metadata[header]["unique_values"]) == 2 and "" not in column_metadata[header]["unique_values"]:
			if "0" and "1" in column_metadata[header]["unique_values"]:
				column_metadata[header]["integer_count"] = 0
				for i in range(0,len(row_metadata[header])):
					row_metadata[header][i]["is_boolean"] = True
					row_metadata[header][i]["is_integer"] = False
					column_metadata[header]["boolean_count"] += 1
			elif column_metadata[header]["boolean_count"] == 0:
				column_metadata[header]["is_category"] = True
				for i in range(0,len(row_metadata[header])):
					row_metadata[header][i]["is_category"] = True

		del column_metadata[header]["unique_values"]
		for i in range(0,len(row_metadata[header])):
			if not any([
					row_metadata[header][i]["is_integer"],
					row_metadata[header][i]["is_float"],
					row_metadata[header][i]["is_fixed_precision"],
					row_metadata[header][i]["is_boolean"],
					row_metadata[header][i]["is_timestamp"],
					row_metadata[header][i]["is_category"],
			]):
				value:str = row_metadata[header][i]["value"]

				try:
					parsed_date = parser.parse(value)
					parsed_date = datetime.replace(parsed_date, tzinfo=timezone.utc)
					current_time = datetime.now(tz=timezone.utc)
					if current_time > parsed_date:
						row_metadata[header][i]["is_date"] = True
						column_metadata[header]["date_count"] += 1
				except ParserError:
					if not row_metadata[header][i]["is_null"]:
						row_metadata[header][i]["is_string"] = True
						column_metadata[header]["string_count"] += 1

			if not any([
				row_metadata[header][i]["is_integer"],
				row_metadata[header][i]["is_float"],
				row_metadata[header][i]["is_fixed_precision"],
				row_metadata[header][i]["is_boolean"],
				row_metadata[header][i]["is_string"],
				row_metadata[header][i]["is_timestamp"],
				row_metadata[header][i]["is_category"],
				row_metadata[header][i]["is_date"],
				row_metadata[header][i]["is_null"],
			]):
				row_metadata[header][i]["is_string"] = True
				column_metadata[header]["string_count"] += 1

		types_present = [
			bool(column_metadata[header]["integer_count"]),
			bool(column_metadata[header]["float_count"]),
			bool(column_metadata[header]["decimal_count"]),
			bool(column_metadata[header]["boolean_count"]),
			bool(column_metadata[header]["timestamp_count"]),
			bool(column_metadata[header]["date_count"]),
			bool(column_metadata[header]["string_count"]),
		]

		if sum(types_present) > 1:
			column_metadata[header]["mixed_dtypes"] = True

		if column_metadata[header]["integer_count"] > 0 and column_metadata[header]["integer_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "integer"
		elif column_metadata[header]["float_count"] > 0 and column_metadata[header]["float_count"] >= max([column_metadata[header]["integer_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "float"
		elif column_metadata[header]["decimal_count"] > 0 and column_metadata[header]["decimal_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["integer_count"]]):
			column_metadata[header]["majority_type"] = "decimal"
		elif column_metadata[header]["boolean_count"] > 0 and column_metadata[header]["boolean_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["integer_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "boolean_"
		elif column_metadata[header]["timestamp_count"] > 0 and column_metadata[header]["timestamp_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["integer_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "timestamp"
		elif column_metadata[header]["date_count"] > 0 and column_metadata[header]["date_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["integer_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "date"
		elif column_metadata[header]["string_count"] > 0 and column_metadata[header]["string_count"] >= max([column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["integer_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "string"
		elif column_metadata[header]["null_count"] > 0 and column_metadata[header]["null_count"] >= max([column_metadata[header]["integer_count"], column_metadata[header]["float_count"], column_metadata[header]["boolean_count"], column_metadata[header]["string_count"], column_metadata[header]["date_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["decimal_count"]]):
			column_metadata[header]["majority_type"] = "null"
		else:
			raise RuntimeError("unable to determine majority type: item: %s int: %s float: %s decimal: %s boolean: %s timestamp: %s date: %s string: %s null: %s\n%s" % (column_metadata[header]["item_count"], column_metadata[header]["integer_count"], column_metadata[header]["float_count"], column_metadata[header]["decimal_count"], column_metadata[header]["boolean_count"], column_metadata[header]["timestamp_count"], column_metadata[header]["date_count"], column_metadata[header]["string_count"], column_metadata[header]["null_count"], row_metadata[header]))
		
	return row_metadata, column_metadata

def clean_data_from_csv(row_metadata:dict, column_metadata:dict, headers:list[str], rounding_precision:float=0.003) -> tuple[dict, dict]:
	"""
		Clean the data imported from a CSV file by handling columns containing multiple data types and non-standard date formats.
		Parameters
		----------
			row_metadata: dict[str,Any]
				Contains row data and metadata from an imported CSV file
			column_metadata: dict[str,Any]
				Contains column metadata from an imported CSV file
			headers: list[str]
				Names of the columns from an imported CSV file
			rounding_precision: float
				Floats containing fractional values less than this will be rounded to the nearest integer
		Returns
		-------
			tuple[dict, dict]
	"""
	for header in headers:
		if column_metadata[header]["mixed_dtypes"]:
			if column_metadata[header]["majority_type"] == "float":
				for i in range(0, len(row_metadata[header])):
					value = row_metadata[header][i]["value"]
					if row_metadata[header][i]["is_integer"]:
						if float(value).is_integer():
							row_metadata[header][i]["value"] = str(float(value))
							row_metadata[header][i]["is_integer"] = False
							row_metadata[header][i]["is_float"] = True
							column_metadata[header]["float_count"] += 1
							column_metadata[header]["integer_count"] -= 1
				
				if column_metadata[header]["float_count"] == column_metadata[header]["item_count"] - column_metadata[header]["null_count"]:
						column_metadata[header]["mixed_dtypes"] = False
						column_metadata[header]["majority_type"] = "float"
				else:
					print(column_metadata[header])

			elif column_metadata[header]["majority_type"] == "integer":

				for i in range(0, len(row_metadata[header])):
					value = row_metadata[header][i]["value"]
					if row_metadata[header][i]["is_float"] and not row_metadata[header][i]["is_fixed_precision"]:
						whole_number, fraction = value.split(".")
						fraction = float("."+fraction)

						if fraction >= 0.5:
							dist_from_nearest_int = 1 - fraction
						elif fraction < 0.5:
							dist_from_nearest_int = 0 - fraction
						else:
							dist_from_nearest_int = 0.0

						if abs(dist_from_nearest_int) <= rounding_precision:
							if dist_from_nearest_int < 0.0:
								row_metadata[header][i]["value"] = whole_number
							else:
								row_metadata[header][i]["value"] = str(int(whole_number) + 1)
							column_metadata[header]["float_count"] -= 1
							column_metadata[header]["integer_count"] += 1
							row_metadata[header][i]["is_integer"] = True
							row_metadata[header][i]["is_float"] = False
						else:
							for j in range(0,len(row_metadata[header])):
								if row_metadata[header][j]["is_integer"]:
									column_metadata[header]["float_count"] += 1
									column_metadata[header]["integer_count"] -= 1
									row_metadata[header][j]["is_integer"] = False
									row_metadata[header][j]["is_float"] = True
							
							if column_metadata[header]["float_count"] == column_metadata[header]["item_count"] - column_metadata[header]["null_count"]:
								column_metadata[header]["mixed_dtypes"] = False
								column_metadata[header]["majority_type"] = "float"
							break

					if row_metadata[header][i]["is_timestamp"]:
						row_metadata[header][i]["is_timestamp"] = False
						column_metadata[header]["timestamp_count"] -= 1
						column_metadata[header]["integer_count"] += 1

					if column_metadata[header]["integer_count"] == column_metadata[header]["item_count"] - column_metadata[header]["null_count"]:
						column_metadata[header]["mixed_dtypes"] = False
						column_metadata[header]["majority_type"] = "integer"
			
			#elif column_metadata[header]["date_count"] > 0 and column_metadata[header]["date_count"] >= column_metadata[header]["item_count"] - column_metadata[header]["date_count"] - column_metadata[header]["null_count"]:
			#	for i in range(0, len(row_metadata[header])):
			#		value = row_metadata[header][i]["value"]
			#		if value:
			#			try:
			#				parsed_date = parser.parse(value)
			#				parsed_date = datetime.replace(parsed_date, tzinfo=timezone.utc)
			#				current_time = datetime.now(tz=timezone.utc)
			#				if current_time > parsed_date:
			#					row_metadata[header][i]["value"] = parsed_date.isoformat()
			#			except ParserError:
			#				continue
		else:
			if column_metadata[header]["date_count"] > 0 and column_metadata[header]["date_count"] >= column_metadata[header]["item_count"] - column_metadata[header]["date_count"] - column_metadata[header]["null_count"]:
				for i in range(0, len(row_metadata[header])):
					value = row_metadata[header][i]["value"]
					if value:
						try:
							parsed_date = parser.parse(value, yearfirst=True, default=datetime(1970,1,1))
							parsed_date = datetime.replace(parsed_date, tzinfo=timezone.utc)
							current_time = datetime.now(tz=timezone.utc)
							if current_time > parsed_date:
								row_metadata[header][i]["value"] = parsed_date.isoformat()
						except ParserError:
							continue

	return row_metadata, column_metadata

DTYPE_MAP = {
	"integer": int,
	"float": float,
	"string": str,
	"boolean": bool,
	"timestamp": int,
	"decimal": Decimal,
	"date": type(pd.Timestamp(2001,1,1,tzinfo=timezone.utc)),
	
}
DTYPE_LIST = [
	int,
	float,
	str,
	bool,
	int,
	Decimal,
	type(pd.Timestamp(2001,1,1,tzinfo=timezone.utc)),
]

def fill_null_cells(row_metadata, column_metadata, header, method:Literal["ffill", "bfill", "same", "choose", "zero", "median", "mean", "average"], dtype:Literal["integer", "float", "decimal", "string", "boolean", "date", "timestamp", "null"]|None=None, infer_dtype=False, fill_value=None, date_range:dict[str,pd.Timestamp|None]|None=None, dtype_for_nulls:Literal["integer", "float", "string", "decimal", "boolean", "timestamp","date"]|None=None):
	"""
		Fill null cells according to the specified method, and null columns according both the specified method data type.
	"""
	def _fill_with_integers():
		nonlocal fill_value
		if method == "zero":
			s.fillna(0, inplace=True)
		elif method == "ffill":
			s.ffill(inplace=True)
		elif method == "bfill":
			s.bfill(inplace=True)
		elif method == "median":
			s.fillna(round(s.median()), inplace=True)
		elif method == "mean":
			s.fillna(round(s.mean()), inplace=True)
		elif method == "average":
			s.fillna(round(s.size/s.sum()), inplace=True)
		elif method == "same":
			for i in range(0,len(row_metadata[header])):
				if row_metadata[header][i]["value"]:
					fill_value = row_metadata[header][i]["value"]
					break
			s.fillna(fill_value, inplace=True)
		elif method == "choose":
			if not isinstance(fill_value, int):
				raise ValueError("fill value '%s' must be of type 'int'" % fill_value)
			s.fillna(fill_value, inplace=True)
		
		data = [item[1].tolist() if not type(item[1]) == type(pd.NA) else item[1] for item in s.items()]
		for i in range(0,len(row_metadata[header])):
			if isinstance(data[i], int) and not row_metadata[header][i]["value"]:
				row_metadata[header][i]["value"] = str(data[i])
				column_metadata[header]["null_count"] -= 1
				column_metadata[header]["integer_count"] += 1
			#elif isinstance(s.array[i], np.int64) and not row_metadata[header][i]["value"]:
			#	row_metadata[header][i]["value"] = s.array[i] 
			#	column_metadata[header]["null_count"] -= 1
			#	column_metadata[header]["integer_count"] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False

	def _fill_with_floats():
		nonlocal fill_value
		if method == "zero":
			s.fillna(0.0, inplace=True)
		elif method == "ffill":
			s.ffill(inplace=True)
		elif method == "bfill":
			s.bfill(inplace=True)
		elif method == "median":
			s.fillna(round(s.median(), ndigits=5), inplace=True)
		elif method == "mean":
			s.fillna(round(s.mean(), ndigits=5), inplace=True)
		elif method == "average":
			s.fillna(round(s.size/s.sum(), ndigits=5), inplace=True)
		elif method == "same":
			for i in range(0,len(row_metadata[header])):
				if row_metadata[header][i]["value"]:
					fill_value = row_metadata[header][i]["value"]
					break
			s.fillna(fill_value, inplace=True)
		elif method == "choose":
			if not isinstance(fill_value, float):
				raise ValueError("fill value '%s' must be of type 'float'" % fill_value)
			s.fillna(fill_value, inplace=True)
		data = [item[1].tolist() if not type(item[1]) == type(pd.NA) else item[1] for item in s.items()]
		for i in range(0,len(row_metadata[header])):
			if isinstance(data[i], float) and not row_metadata[header][i]["value"]:	
				row_metadata[header][i]["value"] = str(data[i])
				column_metadata[header]["null_count"] -= 1
				column_metadata[header]["float_count"] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False
	def _fill_with_decimals():
		raise NotImplementedError("not implemented")
	def _fill_with_booleans():
		raise NotImplementedError("not implemented")
	def _fill_with_strings():
		nonlocal fill_value
		if method == "ffill":
			s.ffill(inplace=True)
		elif method == "bfill":
			s.bfill(inplace=True)
		elif method == "choose":
			if not isinstance(fill_value, str):
				raise ValueError("fill value '%s' must be of type 'str'" % fill_value)
			s.fillna(fill_value, inplace=True)
		elif method == "same":
			for i in range(0,len(row_metadata[header])):
				if row_metadata[header][i]["value"]:
					fill_value = row_metadata[header][i]["value"]
					break
			s.fillna(fill_value, inplace=True)

		data = []
		for item in s.items():
			if type(item[1]) == type(str()) or type(item[1]) == type(pd.NA):
				data.append(item[1])
			else:
				data.append(item[1].tolist())

		for i in range(0,len(row_metadata[header])):
			if isinstance(data[i], str) and not row_metadata[header][i]["value"]:		
				row_metadata[header][i]["value"] =str(data[i])
				column_metadata[header]["null_count"] -= 1
				column_metadata[header]["string_count"] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False
	def _fill_with_dates():
		if method == "ffill":
			null_items = s.isna()

			if null_items.array[0]:
				s.array[0] = pd.Timestamp(year=date_range["start"].year, month=date_range["start"].month, day=date_range["start"].day, tzinfo=timezone.utc)
				null_items.array[0] = False

			for i in range(0, s.size):
				if i+1 < s.size and not null_items.array[i] and null_items.array[i+1]:
					if s.array[i].month < 12:
						s.array[i+1] = pd.Timestamp(year=s.array[i].year, month=s.array[i].month + 1, day=1, tzinfo=timezone.utc)
						null_items.array[i+1] = False
					else:
						s.array[i+1] = pd.Timestamp(year=s.array[i].year + 1, month=1, day=1, tzinfo=timezone.utc)
						null_items.array[i+1] = False

		if method == "bfill":
			null_items = s.isna()

			if null_items.array[-1]:
				s.array[-1] = pd.Timestamp(year=date_range["end"].year, month=date_range["end"].month, day=date_range["end"].day, tzinfo=timezone.utc)
				null_items.array[-1] = False

			for i in reversed(range(0,s.size)):
				if i-1 > s.size and not null_items.array[i] and null_items.array[i-1]:
					if s.array[i].month > 1:
						s.array[i-1] = pd.Timestamp(year=s.array[i].year, month=s.array[i].month - 1, day=1, tzinfo=timezone.utc)
					else:
						s.array[i-1] = pd.Timestamp(year=s.array[i].year - 1, month=12, day=1, tzinfo=timezone.utc)
						null_items.array[i-1] = False

		for i in range(0,len(row_metadata[header])):
			if isinstance(s.array[i], type(pd.Timestamp(2001,1,1, tzinfo=timezone.utc))) and not row_metadata[header][i]["value"]:		
				row_metadata[header][i]["value"] = s.array[i].isoformat()
				column_metadata[header]["null_count"] -= 1
				column_metadata[header]["date_count"] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False
	def _fill_with_timestamps():
		nonlocal fill_value
		if method == "zero":
			s.fillna(0, inplace=True)
		elif method == "ffill":
			s.ffill(inplace=True)
		elif method == "bfill":
			s.bfill(inplace=True)
		elif method == "median":
			s.fillna(round(s.median()), inplace=True)
		elif method == "mean":
			s.fillna(round(s.mean()), inplace=True)
		elif method == "average":
			s.fillna(round(s.size/s.sum()), inplace=True)
		elif method == "same":
			for i in range(0,len(row_metadata[header])):
				if row_metadata[header][i]["value"]:
					fill_value = row_metadata[header][i]["value"]
					break
			s.fillna(fill_value, inplace=True)
		elif method == "choose":
			if not isinstance(fill_value, int):
				raise ValueError("fill value '%s' must be of type 'int'" % fill_value)
			s.fillna(fill_value, inplace=True)
		data = [item[1].tolist() if not type(item[1]) == type(pd.NA) else item[1] for item in s.items()]
		for i in range(0,len(row_metadata[header])):
			if isinstance(data[i], int) and not row_metadata[header][i]["value"]:		
				row_metadata[header][i]["value"] = str(data[i]) 
				column_metadata[header]["null_count"] -= 1
				column_metadata[header]["timestamp_count"] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False
	def _fill_null_columns_with_any():
		nonlocal fill_value
		nonlocal dtype_for_nulls
		count_type = "%s_count" % dtype_for_nulls
		
		if method == "choose":
			s.fillna(fill_value, inplace=True)
		elif method == "zero":
			if dtype_for_nulls == "integer":
				s.fillna(0, inplace=True)
			elif dtype_for_nulls == "float":
				s.fillna(0.0, inplace=True)
		elif method == "ffill":
			if dtype_for_nulls == "date":
				_fill_with_dates()
		
		data = []
		for item in s.items():
			if type(item[1]) in DTYPE_LIST or type(item[1]) == type(pd.NA):
				data.append(item[1])
			else:
				data.append(item[1].tolist())
		
		for i in range(0,len(row_metadata[header])):
			if isinstance(data[i], DTYPE_MAP[dtype_for_nulls]) and not row_metadata[header][i]["value"]:		
				row_metadata[header][i]["value"] = str(data[i])
				column_metadata[header]["null_count"] -= 1
				column_metadata[header][count_type] += 1
			if column_metadata[header]["null_count"] == 0:
				column_metadata[header]["has_null_values"] = False
				column_metadata[header]["majority_type"] = dtype_for_nulls
	
	if not column_metadata[header]["has_null_values"]:
		return row_metadata, column_metadata
	
	if infer_dtype:
		dtype = column_metadata[header]["majority_type"]
			
	if dtype == "integer":
		if method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same" and column_metadata[header]["unique_value_count"] != 1:
			raise ValueError("cannot fill with same value; number of unique values is not 1")
		
		s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.Int64Dtype())
		_fill_with_integers()
	
	elif dtype == "float":
		if method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same" and column_metadata[header]["unique_value_count"] != 1:
			raise ValueError("cannot fill with same value; number of unique values is not 1")
		
		s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.Float64Dtype())
		_fill_with_floats
	
	elif dtype == "decimal":
		if method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		_fill_with_decimals()
	
	elif dtype == "boolean":
		if method in ["zero", "median", "mean", "average"]:
			raise ValueError("cannot use numerical fill method '%s' on column of strings" % method)
		elif method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same":
			raise ValueError("cannot fill boolean column with the same value")
		
		s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.BooleanDtype())
		_fill_with_booleans
	
	elif dtype == "string":
		if method in ["zero", "median", "mean", "average"]:
			raise ValueError("cannot use numerical fill method '%s' on column of strings" % method)
		elif method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same" and column_metadata[header]["unique_value_count"] != 1:
			raise ValueError("cannot fill with same value; number of unique values is not 1")
		
		s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.StringDtype())
		_fill_with_strings()

	elif dtype == "date":
		if method in ["zero", "median", "mean", "average"]:
			raise ValueError("cannot use numerical fill method '%s' on column of dates" % method)
		elif method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same" and column_metadata[header]["unique_value_count"] != 1:
			raise ValueError("cannot fill with same value; number of unique values is not 1")
		
		s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype="datetime64[ms, UTC]")
		_fill_with_dates()

	elif dtype == "timestamp":
		if method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "same" and column_metadata[header]["unique_value_count"] != 1:
			raise ValueError("cannot fill with same value; number of unique values is not 1")
		
		_fill_with_timestamps()

	elif dtype == "null":
		if method in ["median", "mean", "average"]:
			raise ValueError("cannot use numerical fill method '%s' on column of null values" % method)
		elif method in ["ffill", "bfill"] and not date_range:
			raise ValueError("using fill method '%s' for dates on a null column requires a date range to be provided")
		elif method in ["same"]:
			raise ValueError("cannot use fill method '%s' on column of null values" % method)
		elif method == "choose" and not fill_value:
			raise ValueError("must provide 'fill_value' for the 'choose' method")
		elif method == "choose" and fill_value and not dtype_for_nulls:
			raise ValueError("must provide dtype of fill value to place in column")
		
		if dtype_for_nulls == "integer":
			s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.Int64Dtype())
		elif dtype_for_nulls == "float":
			s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.Float64Dtype())
		elif dtype_for_nulls == "decimal":
			raise NotImplementedError("not implemented")
		elif dtype_for_nulls == "boolean":
			raise NotImplementedError("not implemented")
		elif dtype_for_nulls == "string":
			s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.StringDtype())
		elif dtype_for_nulls == "date":
			s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype="datetime64[ms, UTC]")
		elif dtype_for_nulls == "timestamp":
			s = pd.Series({i: row_metadata[header][i]["value"] if row_metadata[header][i]["value"] else None for i in range(0,len(row_metadata[header]))},dtype=pd.Int64Dtype())

		_fill_null_columns_with_any()
	return row_metadata, column_metadata

PANDAS_DTYPES_MAP = {
	"integer": "Int64",
	"float": "Float64",
	"string": "string",
	"boolean": "boolean",
}

def generate_dtype_mappings(column_metadata:dict, headers) -> dict[str,dict]:
	"""
		Uses column metadata to generate column/type mappings for use with `pandas`.
		Should be called only after `analyze_data_from_csv`, `clean_data_from_csv`, and `fill_null_cells`
		has been used.
	"""
	mappings = {"initial": {}, "after": {}}
	for header in headers:
		majority_dtype = column_metadata[header]["majority_type"]
		if column_metadata[header]["is_category"]:
			mappings["initial"][header] = "category"
		elif majority_dtype == "integer":
			mappings["initial"][header] = PANDAS_DTYPES_MAP[majority_dtype]
		elif majority_dtype == "float":
			mappings["initial"][header] = PANDAS_DTYPES_MAP[majority_dtype]
		elif majority_dtype == "string":
			mappings["initial"][header] = PANDAS_DTYPES_MAP[majority_dtype]
		elif majority_dtype == "boolean":
			mappings["initial"][header] = PANDAS_DTYPES_MAP[majority_dtype]
		elif majority_dtype == "decimal":
			mappings["after"][header] = {
					"format": "decimal",
				}
		elif majority_dtype == "date":
			mappings["after"][header] = {
				"format": "datetime",
				"origin": "unix",
				"unit": "us",
				"is_utc": True,
			}
		elif majority_dtype == "timestamp":
			mappings["after"][header] = {
				"format": "datetime",
				"origin": "unix",
				"unit": "ms",#ts_precision,
				"is_utc": True,
			}
		else:
			mappings["initial"][header] = "object"
	return mappings

def remove_duplicate_columns(df:DataFrame, headers:list[str], exclude:tuple[str]|None=None) -> DataFrame:
	"""
		Removes duplicate columns from a DataFrame, both by value and by label.
	"""
	try:
		unique_columns = set()
		duplicate_columns = set()
		
		df_cols = [df.iloc[:,i] for i in range(0,len(df.columns))]
		is_duplicate_columns = df.columns.duplicated().tolist()

		new_df_cols:list[pd.Series] = []
		for col, is_duplicate in zip(df_cols, is_duplicate_columns):
			if not is_duplicate:
				new_df_cols.append(col)

		df = pd.concat(new_df_cols, axis=1)
		for header in headers:
			for sub_header in headers:
				if not header.startswith(exclude) and not sub_header.startswith(exclude) and header in df and sub_header in df:
					if header != sub_header and sub_header not in unique_columns and header not in duplicate_columns and all(df[header] == df[sub_header]):
						unique_columns.add(header)
						duplicate_columns.add(sub_header)

		for column in duplicate_columns:
			df.drop(column, axis=1, inplace=True)
		for header in headers:
			if header.startswith("Date:"):
				df.rename(columns={header: "date"}, inplace=True)
			elif header.startswith("Source:"):
				df.rename(columns={header: "source"}, inplace=True)
	except ValueError:

		pass
	return df


def apply_mappings_to_dataframe(row_metadata:dict, headers:list[str], mappings:dict) -> DataFrame:
	"""
		Creates a DataFrame with specified column/type mappings.
	"""
	df = pd.read_csv(export_to_buffer(row_metadata, headers), delimiter=",", dtype=mappings["initial"])
	if mappings["after"]:
		columns = list(mappings["after"])
		for column in columns:
			dtype = mappings["after"][column]["format"]
			if dtype == "datetime":
				ts_origin = mappings["after"][column]["origin"]
				ts_unit = mappings["after"][column]["unit"]
				is_utc = mappings["after"][column]["is_utc"]
				df[column] = pd.to_datetime(df[column], origin=ts_origin, unit=ts_unit, utc=is_utc)
			elif dtype == "decimal":
				df[column] = df[column].apply(Decimal)
	return df

def add_rows(df:DataFrame, headers:list[str], name:str, fill_string:str="", fill_int:int=0, fill_float:float=0.0, date_range={"start": pd.Timestamp(year=2001, month=1, day=1, tzinfo=timezone.utc), "end": pd.Timestamp(year=2025, month=10, day=1, tzinfo=timezone.utc)}) -> pd.DataFrame:
	"""
		Adds additional rows to a dataframe based on a date range.
	"""
	
	dIndex = pd.date_range(date_range["start"], date_range["end"], freq="MS")
	
	date_headers = [header for header in headers if header.startswith("Date:")]
	source_headers = [header for header in headers if header.startswith("Source:")]
	value_headers = [header for header in headers if header.startswith("Value:")]
	id_headers = [header for header in headers if header.startswith("place")]
	id_values = [(id_header, df[id_header].tolist()[0]) for id_header in id_headers]
	column_dtypes = {header: str(df[header].dtype) for header in headers}

	date_count = len(dIndex)
	row_counts = [sum(df[header].notna()) + sum(df[header].isna()) for header in headers]

	if row_counts.count(row_counts[0]) == len(row_counts):
		missing_row_num = date_count - row_counts[0]
		new_rows = []
		for _ in range(0,missing_row_num):
			new_rows.append({header: None for header in headers})
		df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

	else:
		raise ValueError("not all columns in dataframe are of equal length:\n %s" % row_counts)
	
	for d_header in date_headers:
		null_dates = df[d_header].isna()
		for i in range(len(null_dates)):
			if null_dates.array[i]:
				for index in dIndex:
					if index not in df[d_header].array:
						#print("Date column %s, row %s, is empty; inserting %s" % (d_header, i, index))
						s = df[d_header]
						s.iloc[i] = index
						df[d_header] = s.astype(dtype=column_dtypes[d_header])
						break
		if d_header == date_headers[0]:
			df.sort_values(by=d_header, ignore_index=True, inplace=True)
		else:
			s = df[d_header]
			s.sort_values(ignore_index=True, inplace=True)
			df[d_header] = s
	
	for s_header in source_headers:
		null_sources = df[s_header].isna()
		for i in range(0, len(null_sources)):
			if null_sources[i]:
				#print("Source column %s, row %s, is empty; inserting %s" % (s_header, i, fill_string))
				s = df[s_header] 
				s.iloc[i] = fill_string
				df[s_header] = s.astype(dtype=column_dtypes[s_header])
		del null_sources
	for v_header in value_headers:
		null_values = df[v_header].isna()
		for i in range(0,len(null_values)):
			if null_values[i] and column_dtypes[v_header].lower().startswith("float"):
				#print("Value column %s, row %s, is empty; inserting %s" % (v_header, i, fill_float))
				s = df[v_header]
				s.iloc[i] = fill_float
				df[v_header] = s.astype(dtype=column_dtypes[v_header])
			elif null_values[i] and column_dtypes[v_header].lower().startswith("int"):
				#print("Value column %s, row %s, is empty; inserting %s" % (v_header, i, fill_int))
				s = df[v_header]
				s.iloc[i] = fill_int
				df[v_header] = s.astype(dtype=column_dtypes[v_header])
		del null_values
	for i_header, i_value in id_values:
		null_ids = df[i_header].isna()
		for i in range(0,len(null_ids)):
			if null_ids[i]:
				#print("ID column %s, row %s, is empty; inserting %s" % (i_header, i, i_value))
				s = df[i_header]
				s.iloc[i] = i_value
				df[i_header] = s.astype(dtype=column_dtypes[i_header])
		del null_ids

	return df