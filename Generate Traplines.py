# -----
#
# ** Requires input boundary shp or feature class **
#
# Generate traplines at desired width + interval (m), rotate the lines to desired direction, then clip and export.
# Output data in WGS84 shp format for use on Garmin GPS.
#
# Developed for Vector Control Services by John Stowell, WCRC, 2020.
# 
# 
# -----

# Import system modules and arcpy
#
import sys
import string
import os
import glob
import arcpy
import shutil
import time

# Get/set our tool parameters
#
bdy_poly = arcpy.GetParameterAsText(0) # Input boundary - to generate traplines inside of
bdy_name = arcpy.GetParameterAsText(1) # eg. Rotomanu
line_spacing = arcpy.GetParameterAsText(2) # eg. 350  (metres)
point_interval = arcpy.GetParameterAsText(3) # eg. 100  (metres)
rotation_val = arcpy.GetParameterAsText(4) # eg. 90  (degrees)
out_folder = arcpy.GetParameterAsText(5) # Output folder for WGS84 shp files
arcpy.AddMessage('\n')

# Set the ArcMap workspace and main gdb for processing
#
tmp_folder = os.path.join(out_folder, 'tmp')
if not os.path.exists(tmp_folder):
    #shutil.rmtree(tmp_folder)
    os.makedirs(tmp_folder)
os.chdir(tmp_folder)
arcpy.CreateFileGDB_management(tmp_folder, 'tmp_processing.gdb')

tmp_gdb = os.path.join(tmp_folder, 'tmp_processing.gdb')
bdy_fc_path = os.path.join(tmp_gdb, bdy_name+'_bdy')
arcpy.AddMessage('>> Created temporary workspace and gdb: \n{0}'.format(tmp_gdb))
arcpy.AddMessage('\n')

# Copy bdy fc, set env settings and get extent of input feature class
arcpy.CopyFeatures_management(bdy_poly, bdy_fc_path)
arcpy.AddMessage('>> Copied input features to temporary gdb.')
time.sleep(5)

arcpy.env.workspace = tmp_gdb
arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(2193) # NZTM 2000

tmp_fc_list = arcpy.ListFeatureClasses()
arcpy.AddMessage('Feature classes: {0}'.format(tmp_fc_list))
arcpy.AddMessage('\n')
bdy_fc = tmp_fc_list[0] # 0 is our boundary fc, since we only copied one feature class initially

for row in arcpy.da.SearchCursor(bdy_fc, ['SHAPE@', 'SHAPE@XY']):
    bdy_fc_extent = row[0].extent # Get fc extent data
    bdy_fc_centroid = row[1] # Get fc centroid for use as pivot point [1480729.1661422371, 5277623.892574378]
arcpy.AddMessage('Extent: {0}'.format(bdy_fc_extent.JSON))
arcpy.AddMessage('Centroid: {0}'.format(bdy_fc_centroid))

xmin = bdy_fc_extent.XMin 
ymin = bdy_fc_extent.YMin 
xmax = bdy_fc_extent.XMax 
ymax = bdy_fc_extent.YMax 


# Create fishnet grid lines at set line spacing ...
# Variables below are using some offset values to dynamically buffer the input extent (for NZTM x/y coords)
# This should help to accomodate funny shaped/oriented input polygons
# 
origin_coord = '{0} {1}'.format(xmin-10000, ymin-10000) 
y_axis_coord = '{0} {1}'.format(xmin-10000, ymin-10000+10) 
corner_coord = '{0} {1}'.format(xmax+10000, ymax+10000) 
cell_width = line_spacing
cell_height = 30000
labels = 'NO_LABELS'
geom = 'POLYLINE'
tmp_fishnet_path = os.path.join(tmp_gdb, bdy_name+'_fishnet') 
arcpy.CreateFishnet_management(tmp_fishnet_path, origin_coord, y_axis_coord, cell_width, cell_height, 0, 0, corner_coord, labels, '#', geom)
time.sleep(5)
arcpy.AddMessage('>> Created fishnet in tmp gdb')
arcpy.AddMessage('\n')


# Rotate grid lines based on a pivot point - using the input fc centroid
# Also requires us to convert to raster, rotate, and then convert back to vector
# (As there is no built in vector rotation tool ...)
#
arcpy.AddMessage('>> Now running rotation process...')
arcpy.AddMessage('\n')
pivot_point = '{0} {1}'.format(bdy_fc_centroid[0], bdy_fc_centroid[1]) # X Y
out_raster = os.path.join(tmp_gdb, bdy_name+'_raster')
out_raster_rotated = os.path.join(tmp_gdb, bdy_name+'_raster_r')
tmp_fishnet_rotated = os.path.join(tmp_gdb, bdy_name+'_fishnet_r') 
# Convert to raster, rotate, and convert back to polyline (use 10m to keep our raster cells separate)
arcpy.PolylineToRaster_conversion(tmp_fishnet_path, 'OID', out_raster, 'MAXIMUM_LENGTH', 'NONE', 10)
arcpy.Rotate_management(out_raster, out_raster_rotated, rotation_val, pivot_point, 'NEAREST')
arcpy.RasterToPolyline_conversion(out_raster_rotated, tmp_fishnet_rotated, 'ZERO', 0, 'SIMPLIFY')
arcpy.AddMessage('Rotated data by specified value: {0} degrees'.format(rotation_val))
# Perform a real simplification on the layer - to tidy up the lines
tmp_fishnet_rotated_simpl = tmp_fishnet_rotated+'_s'
arcpy.SimplifyLine_cartography(tmp_fishnet_rotated, tmp_fishnet_rotated_simpl, 'POINT_REMOVE', 10)
time.sleep(5)
arcpy.AddMessage('Simplified/cleaned up data')
arcpy.AddMessage('\n')


# Clip rotated lines to input boundary
# 
tmp_fishnet_clip = os.path.join(tmp_gdb, bdy_name+'_fishnet_r_s_c')
arcpy.Clip_analysis(tmp_fishnet_rotated_simpl, bdy_fc_path, tmp_fishnet_clip)
arcpy.AddMessage('>> Clipped new trap lines to input boundary')
arcpy.AddMessage('\n')


# Generate points along the clipped lines at set point intervals
# 
tmp_pts_along_line = os.path.join(tmp_gdb, bdy_name+'_fishnet_r_s_c_pts')
dist = '{0} meters'.format(point_interval) # US formatted spelling...
arcpy.GeneratePointsAlongLines_management(tmp_fishnet_clip, tmp_pts_along_line, 'DISTANCE', Distance=dist)
arcpy.AddMessage('>> Generated points along lines at interval: {0}'.format(dist))
arcpy.AddMessage('\n')


# Convert projection WGS84
#
tmp_pts_along_line_WGS = os.path.join(tmp_gdb, bdy_name+'_fishnet_r_s_c_pts_WGS')
WGS84 = arcpy.SpatialReference(4326) # GCS WGS 1984
# transform_method = 'NZGD_2000_To_WGS_1984_1' # this isn't required in the tool
arcpy.Project_management(tmp_pts_along_line, tmp_pts_along_line_WGS, WGS84)
arcpy.AddMessage('>> Converted data to WGS84 coordinate system')
arcpy.AddMessage('\n')

# Export to output shp folder
#
arcpy.FeatureClassToShapefile_conversion(tmp_pts_along_line_WGS, out_folder)
arcpy.AddMessage('>> Exported shp to: {0}'.format(out_folder))
arcpy.AddMessage('\n')