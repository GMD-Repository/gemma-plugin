<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="AllStyleCategories" hasScaleBasedVisibilityFlag="0" labelsEnabled="1">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
    <Private>0</Private>
  </flags>
  <renderer-v2 type="singleSymbol" symbollevels="0" enablegroupby="0" referencescale="-1">
    <symbols>
      <symbol type="fill" name="0" alpha="1" clip_to_extent="1" force_rhr="0">
        <layer enabled="1" pass="0" class="SimpleFill" locked="0">
          <Option type="Map">
            <Option type="QString" name="border_width_map_unit_scale" value="3x:0,0,0,0,0,0"/>
            <Option type="QString" name="color" value="255,152,0,40"/>
            <Option type="QString" name="joinstyle" value="bevel"/>
            <Option type="QString" name="offset" value="0,0"/>
            <Option type="QString" name="outline_color" value="245,124,0,255"/>
            <Option type="QString" name="outline_style" value="solid"/>
            <Option type="QString" name="outline_width" value="0.7"/>
            <Option type="QString" name="outline_width_unit" value="MM"/>
            <Option type="QString" name="style" value="solid"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style forcedBold="1" allowHtml="0" previewBkgrdColor="255,255,255,255" textOpacity="1" namedStyle="Bold" fontStrikeout="0" fontLetterSpacing="0" fontSize="9" fontUnderline="0" multilineHeight="1" fontWordSpacing="0" textOrientation="horizontal" fontFamily="Segoe UI" blendMode="0" legendString="Aa" fontItalic="0" fontKerning="1" capitalization="0" forcedItalic="0" useSubstitutions="0" fontWeight="75" textColor="230,81,0,255" fieldName="concat(coalesce(&quot;new_ean&quot;,&quot;ean&quot;,&quot;name&quot;), '\n(', coalesce(&quot;hhcount&quot;,&quot;hh_count&quot;, 0), ' HH)')" isExpression="1" multilineHeightUnit="Percentage" fontSizeUnit="Point">
        <families/>
        <text-buffer bufferColor="255,255,255,255" bufferOpacity="1" bufferSize="1.5" bufferNoFill="1" bufferDraw="1" bufferSizeUnits="MM" bufferJoinStyle="128" bufferSizeMapUnitScale="3x:0,0,0,0,0,0" bufferBlendMode="0"/>
        <text-mask maskType="0" maskSizeMapUnitScale="3x:0,0,0,0,0,0" maskSize="1.5" maskOpacity="1" maskEnabled="0" maskedSymbolLayers="" maskSizeUnits="MM" maskJoinStyle="128"/>
      </text-style>
      <text-format multilineAlign="1" formatNumbers="0" decimals="3" addDirectionSymbol="0" useMaxLineLengthForAutoWrap="1" wrapChar="" leftDirectionSymbol="&lt;" autoWrapLength="0" plussign="0" rightDirectionSymbol="&gt;" placeDirectionSymbol="0" reverseDirectionSymbol="0"/>
      <placement distUnits="MM" repeatDistance="0" geometryGenerator="" lineAnchorPercent="0.5" offsetType="0" xOffset="0" yOffset="0" overlapHandling="PreventOverlap" priority="10" repeatDistanceMapUnitScale="3x:0,0,0,0,0,0" labelOffsetMapUnitScale="3x:0,0,0,0,0,0" distMapUnitScale="3x:0,0,0,0,0,0" lineAnchorTextPoint="CenterOfText" geometryGeneratorType="PointGeometry" rotationUnit="AngleDegrees" centroidInside="0" maxCurvedCharAngleOut="-25" repeatDistanceUnits="MM" maxCurvedCharAngleIn="25" overrunDistanceUnit="MM" predefinedPositionOrder="TR,TL,BR,BL,R,L,TSR,BSR" dist="0" polygonPlacementFlags="2" allowDegraded="0" lineAnchorType="0" quadOffset="4" overrunDistance="0" fitInPolygonOnly="0" lineAnchorClipping="0" placement="0" rotationAngle="0" overrunDistanceMapUnitScale="3x:0,0,0,0,0,0" geometryGeneratorEnabled="0" centroidWhole="0" offsetUnits="MM" layerType="PolygonGeometry" preserveRotation="1" placementFlags="10"/>
      <rendering drawLabels="1" fontMinPixelSize="3" limitNumLabels="0" scaleVisibility="0" mergeLines="0" obstacle="1" obstacleType="1" labelPerPart="0" minFeatureSize="0" fontMaxPixelSize="10000" scaleMax="0" maxNumLabels="2000" unplacedVisibility="0" fontLimitPixelSize="0" zIndex="0" obstacleFactor="0" scaleMin="0" upsidedownLabels="0"/>
    </settings>
  </labeling>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
</qgis>
