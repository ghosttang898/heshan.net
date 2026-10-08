import { formatIpLocation } from "../ipLocation";

export default function IpLocationLabel({ item }) {
  return <span className="ip-location" title="IP 属地为发布时的近似位置，不保证城市准确">IP属地：{formatIpLocation(item)}</span>;
}
