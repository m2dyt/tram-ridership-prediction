import React, { useMemo } from "react";
import { Marker, useMap } from "@vis.gl/react-maplibre";
import Supercluster from "supercluster";
import { ClusterPoint } from "./ClusterPoint";

const radiusPixels = 35;
const zoomLevel = 14; // stops can be clustered up to zoom 14

export const ClusterComponent = ({ data, setPopUpData }) => {
  const { current: mapref } = useMap();

  const [zoom, setZoom] = React.useState(13);
  const [bbox, setBbox] = React.useState([-180, -90, 180, 90]);

  React.useEffect(() => {
    if (!mapref) return;
    const update = () => {
      setZoom(mapref.getZoom());
      const bounds = mapref.getBounds();
      if (bounds) {
          setBbox([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]);
      }
    };
    mapref.on("move", update);
    mapref.on("zoom", update);
    update();
    return () => {
      mapref.off("move", update);
      mapref.off("zoom", update);
    };
  }, [mapref]);

  const features = useMemo(() => {
    return data
      .filter((item) => item.latitude != null && item.longitude != null)
      .map((item) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [item.longitude, item.latitude],
        },
        properties: {
          id: item.id,
          name: item.name
        },
      }));
  }, [data]);

  const index = useMemo(() => {
    const cluster = new Supercluster({
      radius: radiusPixels,
      maxZoom: zoomLevel,
    });
    cluster.load(features);
    return cluster;
  }, [features]);

  const clusters = useMemo(() => {
    return index.getClusters(bbox, Math.floor(zoom));
  }, [index, bbox, zoom]);

  const handleClick = (e, lng, lat, cluster, isCluster) => {
    e.originalEvent.stopPropagation();
    e.originalEvent.preventDefault();

    if (!isCluster) {
      const popUpData = data.find((item) => item.id === cluster.properties?.id);
      setPopUpData({
        lng,
        lat,
        popUpData,
      });
    }

    if (isCluster && mapref) {
      const zoomToExpandCluster = index.getClusterExpansionZoom(
        cluster.properties.cluster_id,
      );
      mapref.flyTo({
        center: [lng, lat],
        zoom: zoomToExpandCluster,
        duration: 1000,
      });
    }
  };

  return (
    <>
      {clusters.map((cluster) => {
        const [lng, lat] = cluster.geometry.coordinates;
        const isCluster = cluster.properties?.cluster;

        return (
          <Marker
            key={
              isCluster ? cluster.properties.cluster_id : cluster.properties.id
            }
            longitude={lng}
            latitude={lat}
            onClick={(e) => handleClick(e, lng, lat, cluster, isCluster)}
          >
            <ClusterPoint isCluster={isCluster} clusterData={cluster} />
          </Marker>
        );
      })}
    </>
  );
};
