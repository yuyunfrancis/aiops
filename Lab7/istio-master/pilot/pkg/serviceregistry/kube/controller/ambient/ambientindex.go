// Copyright Istio Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package ambient

import (
	"net/netip"
	"strings"

	v1 "k8s.io/api/core/v1"
	discovery "k8s.io/api/discovery/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/gateway-api/apis/v1beta1"

	"istio.io/api/label"
	"istio.io/api/meta/v1alpha1"
	networkingclient "istio.io/client-go/pkg/apis/networking/v1"
	securityclient "istio.io/client-go/pkg/apis/security/v1"
	"istio.io/istio/pilot/pkg/features"
	"istio.io/istio/pilot/pkg/model"
	"istio.io/istio/pilot/pkg/serviceregistry/kube/controller/ambient/statusqueue"
	"istio.io/istio/pkg/activenotifier"
	"istio.io/istio/pkg/cluster"
	"istio.io/istio/pkg/config/constants"
	"istio.io/istio/pkg/config/labels"
	"istio.io/istio/pkg/config/schema/gvr"
	"istio.io/istio/pkg/config/schema/kind"
	kubeclient "istio.io/istio/pkg/kube"
	"istio.io/istio/pkg/kube/controllers"
	"istio.io/istio/pkg/kube/kclient"
	"istio.io/istio/pkg/kube/krt"
	"istio.io/istio/pkg/kube/kubetypes"
	"istio.io/istio/pkg/log"
	"istio.io/istio/pkg/maps"
	"istio.io/istio/pkg/network"
	"istio.io/istio/pkg/slices"
	"istio.io/istio/pkg/util/sets"
	"istio.io/istio/pkg/workloadapi"
)

type Index interface {
	Lookup(key string) []model.AddressInfo
	All() []model.AddressInfo
	WorkloadsForWaypoint(key model.WaypointKey) []model.WorkloadInfo
	ServicesForWaypoint(key model.WaypointKey) []model.ServiceInfo
	SyncAll()
	NetworksSynced()
	Run(stop <-chan struct{})
	HasSynced() bool
	model.AmbientIndexes
}

var _ Index = &index{}

type NamespaceHostname struct {
	Namespace string
	Hostname  string
}

func (n NamespaceHostname) String() string {
	return n.Namespace + "/" + n.Hostname
}

type workloadsCollection struct {
	krt.Collection[model.WorkloadInfo]
	ByAddress        krt.Index[networkAddress, model.WorkloadInfo]
	ByServiceKey     krt.Index[string, model.WorkloadInfo]
	ByOwningWaypoint krt.Index[NamespaceHostname, model.WorkloadInfo]
}

type waypointsCollection struct {
	krt.Collection[Waypoint]
}

type servicesCollection struct {
	krt.Collection[model.ServiceInfo]
	ByAddress        krt.Index[networkAddress, model.ServiceInfo]
	ByOwningWaypoint krt.Index[NamespaceHostname, model.ServiceInfo]
}

// index maintains an index of ambient WorkloadInfo objects by various keys.
// These are intentionally pre-computed based on events such that lookups are efficient.
type index struct {
	services  servicesCollection
	workloads workloadsCollection
	waypoints waypointsCollection

	authorizationPolicies krt.Collection[model.WorkloadAuthorization]
	networkUpdateTrigger  *krt.RecomputeTrigger

	statusQueue *statusqueue.StatusQueue

	SystemNamespace string
	DomainSuffix    string
	ClusterID       cluster.ID
	XDSUpdater      model.XDSUpdater
	// Network provides a way to lookup which network a given workload is running on
	Network LookupNetwork
	// LookupNetworkGateways provides a function to lookup all the known network gateways in the system.
	LookupNetworkGateways LookupNetworkGateways
}

type Options struct {
	Client kubeclient.Client

	Revision              string
	SystemNamespace       string
	DomainSuffix          string
	ClusterID             cluster.ID
	XDSUpdater            model.XDSUpdater
	LookupNetwork         LookupNetwork
	LookupNetworkGateways LookupNetworkGateways
	StatusNotifier        *activenotifier.ActiveNotifier
}

func New(options Options) Index {
	a := &index{
		networkUpdateTrigger: krt.NewRecomputeTrigger(false),

		SystemNamespace:       options.SystemNamespace,
		DomainSuffix:          options.DomainSuffix,
		ClusterID:             options.ClusterID,
		XDSUpdater:            options.XDSUpdater,
		Network:               options.LookupNetwork,
		LookupNetworkGateways: options.LookupNetworkGateways,
	}

	filter := kclient.Filter{
		ObjectFilter: options.Client.ObjectFilter(),
	}
	ConfigMaps := krt.NewInformerFiltered[*v1.ConfigMap](options.Client, filter, krt.WithName("ConfigMaps"))

	authzPolicies := kclient.NewDelayedInformer[*securityclient.AuthorizationPolicy](options.Client,
		gvr.AuthorizationPolicy, kubetypes.StandardInformer, filter)
	AuthzPolicies := krt.WrapClient[*securityclient.AuthorizationPolicy](authzPolicies, krt.WithName("AuthorizationPolicies"))

	peerAuths := kclient.NewDelayedInformer[*securityclient.PeerAuthentication](options.Client,
		gvr.PeerAuthentication, kubetypes.StandardInformer, filter)
	PeerAuths := krt.WrapClient[*securityclient.PeerAuthentication](peerAuths, krt.WithName("PeerAuthentications"))

	serviceEntries := kclient.NewDelayedInformer[*networkingclient.ServiceEntry](options.Client,
		gvr.ServiceEntry, kubetypes.StandardInformer, filter)
	ServiceEntries := krt.WrapClient[*networkingclient.ServiceEntry](serviceEntries, krt.WithName("ServiceEntries"))

	workloadEntries := kclient.NewDelayedInformer[*networkingclient.WorkloadEntry](options.Client,
		gvr.WorkloadEntry, kubetypes.StandardInformer, filter)
	WorkloadEntries := krt.WrapClient[*networkingclient.WorkloadEntry](workloadEntries, krt.WithName("WorkloadEntries"))

	gatewayClient := kclient.NewDelayedInformer[*v1beta1.Gateway](options.Client, gvr.KubernetesGateway, kubetypes.StandardInformer, filter)
	Gateways := krt.WrapClient[*v1beta1.Gateway](gatewayClient, krt.WithName("Gateways"))

	gatewayClassClient := kclient.NewDelayedInformer[*v1beta1.GatewayClass](options.Client, gvr.GatewayClass, kubetypes.StandardInformer, filter)
	GatewayClasses := krt.WrapClient[*v1beta1.GatewayClass](gatewayClassClient, krt.WithName("GatewayClasses"))

	servicesClient := kclient.NewFiltered[*v1.Service](options.Client, filter)
	Services := krt.WrapClient[*v1.Service](servicesClient, krt.WithName("Services"))
	Nodes := krt.NewInformerFiltered[*v1.Node](options.Client, kclient.Filter{
		ObjectFilter:    options.Client.ObjectFilter(),
		ObjectTransform: kubeclient.StripNodeUnusedFields,
	}, krt.WithName("Nodes"))
	Pods := krt.NewInformerFiltered[*v1.Pod](options.Client, kclient.Filter{
		ObjectFilter:    options.Client.ObjectFilter(),
		ObjectTransform: kubeclient.StripPodUnusedFields,
	}, krt.WithName("Pods"))

	// TODO: Should this go ahead and transform the full ns into some intermediary with just the details we care about?
	Namespaces := krt.NewInformer[*v1.Namespace](options.Client, krt.WithName("Namespaces"))

	EndpointSlices := krt.NewInformerFiltered[*discovery.EndpointSlice](options.Client, kclient.Filter{
		ObjectFilter: options.Client.ObjectFilter(),
	}, krt.WithName("EndpointSlices"))

	MeshConfig := MeshConfigCollection(ConfigMaps, options)
	Waypoints := a.WaypointsCollection(Gateways, GatewayClasses, Pods)

	// AllPolicies includes peer-authentication converted policies
	AuthorizationPolicies, AllPolicies := PolicyCollections(AuthzPolicies, PeerAuths, MeshConfig, Waypoints)
	AllPolicies.RegisterBatch(PushXds(a.XDSUpdater,
		func(i model.WorkloadAuthorization) (model.ConfigKey, bool) {
			if i.Authorization == nil {
				return model.ConfigKey{}, true // nop, filter this out
			}
			return model.ConfigKey{Kind: kind.AuthorizationPolicy, Name: i.Authorization.Name, Namespace: i.Authorization.Namespace}, false
		}), false)

	serviceEntriesWriter := kclient.NewWriteClient[*networkingclient.ServiceEntry](options.Client)
	servicesWriter := kclient.NewWriteClient[*v1.Service](options.Client)

	// these are workloadapi-style services combined from kube services and service entries
	WorkloadServices := a.ServicesCollection(Services, ServiceEntries, Waypoints, Namespaces)

	WaypointPolicyStatus := WaypointPolicyStatusCollection(
		AuthzPolicies,
		Waypoints,
		Services,
		ServiceEntries,
		Namespaces,
	)

	authorizationPoliciesWriter := kclient.NewWriteClient[*securityclient.AuthorizationPolicy](options.Client)

	if features.EnableAmbientStatus {
		statusQueue := statusqueue.NewQueue(options.StatusNotifier)
		statusqueue.Register(statusQueue, "istio-ambient-service", WorkloadServices, func(info model.ServiceInfo) (kclient.Patcher, []string) {
			// Since we have 1 collection for multiple types, we need to split these out
			if info.Source.Kind == kind.ServiceEntry {
				return kclient.ToPatcher(serviceEntriesWriter), getConditions(info.Source.NamespacedName, serviceEntries)
			}
			return kclient.ToPatcher(servicesWriter), getConditions(info.Source.NamespacedName, servicesClient)
		})
		statusqueue.Register(statusQueue, "istio-ambient-ztunnel-policy", AuthorizationPolicies, func(pol model.WorkloadAuthorization) (kclient.Patcher, []string) {
			return kclient.ToPatcher(authorizationPoliciesWriter), getConditions(pol.Source.NamespacedName, authzPolicies)
		})
		statusqueue.Register(statusQueue, "istio-ambient-waypoint-policy", WaypointPolicyStatus, func(pol model.WaypointPolicyStatus) (kclient.Patcher, []string) {
			return kclient.ToPatcher(authorizationPoliciesWriter), getConditions(pol.Source.NamespacedName, authzPolicies)
		})
		a.statusQueue = statusQueue
	}

	ServiceAddressIndex := krt.NewIndex[networkAddress, model.ServiceInfo](WorkloadServices, networkAddressFromService)
	ServiceInfosByOwningWaypoint := krt.NewIndex(WorkloadServices, func(s model.ServiceInfo) []NamespaceHostname {
		// Filter out waypoint services
		if s.Labels[label.GatewayManaged.Name] == constants.ManagedGatewayMeshControllerLabel {
			return nil
		}
		waypoint := s.Service.Waypoint
		if waypoint == nil {
			return nil
		}
		waypointAddress := waypoint.GetHostname()
		if waypointAddress == nil {
			return nil
		}

		return []NamespaceHostname{{
			Namespace: waypointAddress.Namespace,
			Hostname:  waypointAddress.Hostname,
		}}
	})
	WorkloadServices.RegisterBatch(krt.BatchedEventFilter(
		func(a model.ServiceInfo) *workloadapi.Service {
			// Only trigger push if the XDS object changed; the rest is just for computation of others
			return a.Service
		},
		PushXds(a.XDSUpdater, func(i model.ServiceInfo) (model.ConfigKey, bool) {
			return model.ConfigKey{Kind: kind.Address, Name: i.ResourceName()}, false
		})), false)

	Workloads := a.WorkloadsCollection(
		Pods,
		Nodes,
		MeshConfig,
		AuthorizationPolicies,
		PeerAuths,
		Waypoints,
		WorkloadServices,
		WorkloadEntries,
		ServiceEntries,
		EndpointSlices,
		Namespaces,
	)

	WorkloadAddressIndex := krt.NewIndex[networkAddress, model.WorkloadInfo](Workloads, networkAddressFromWorkload)
	WorkloadServiceIndex := krt.NewIndex[string, model.WorkloadInfo](Workloads, func(o model.WorkloadInfo) []string {
		return maps.Keys(o.Services)
	})
	WorkloadWaypointIndex := krt.NewIndex(Workloads, func(w model.WorkloadInfo) []NamespaceHostname {
		// Filter out waypoints.
		if w.Labels[label.GatewayManaged.Name] == constants.ManagedGatewayMeshControllerLabel {
			return nil
		}
		waypoint := w.Waypoint
		if waypoint == nil {
			return nil
		}
		waypointAddress := waypoint.GetHostname()
		if waypointAddress == nil {
			return nil
		}

		return []NamespaceHostname{{
			Namespace: waypointAddress.Namespace,
			Hostname:  waypointAddress.Hostname,
		}}
	})
	Workloads.RegisterBatch(krt.BatchedEventFilter(
		func(a model.WorkloadInfo) *workloadapi.Workload {
			// Only trigger push if the XDS object changed; the rest is just for computation of others
			return a.Workload
		},
		PushXds(a.XDSUpdater, func(i model.WorkloadInfo) (model.ConfigKey, bool) {
			return model.ConfigKey{Kind: kind.Address, Name: i.ResourceName()}, false
		})), false)

	a.workloads = workloadsCollection{
		Collection:       Workloads,
		ByAddress:        WorkloadAddressIndex,
		ByServiceKey:     WorkloadServiceIndex,
		ByOwningWaypoint: WorkloadWaypointIndex,
	}
	a.services = servicesCollection{
		Collection:       WorkloadServices,
		ByAddress:        ServiceAddressIndex,
		ByOwningWaypoint: ServiceInfosByOwningWaypoint,
	}
	a.waypoints = waypointsCollection{
		Collection: Waypoints,
	}
	a.authorizationPolicies = AllPolicies

	return a
}

func getConditions[T controllers.ComparableObject](name types.NamespacedName, i kclient.Informer[T]) []string {
	o := i.Get(name.Name, name.Namespace)
	if controllers.IsNil(o) {
		return nil
	}
	switch t := any(o).(type) {
	case *v1.Service:
		return slices.Map(t.Status.Conditions, func(c metav1.Condition) string { return c.Type })
	case *networkingclient.ServiceEntry:
		return slices.Map(t.Status.Conditions, (*v1alpha1.IstioCondition).GetType)
	case *securityclient.AuthorizationPolicy:
		return slices.Map(t.Status.Conditions, (*v1alpha1.IstioCondition).GetType)
	default:
		log.Fatalf("unknown type %T; cannot write status", o)
	}
	return nil
}

// Lookup finds all addresses associated with a given key. Many different key formats are supported; see inline comments.
func (a *index) Lookup(key string) []model.AddressInfo {
	// 1. Workload UID
	if w := a.workloads.GetKey(krt.Key[model.WorkloadInfo](key)); w != nil {
		return []model.AddressInfo{workloadToAddressInfo(w.Workload)}
	}

	network, ip, found := strings.Cut(key, "/")
	if !found {
		log.Warnf(`key (%v) did not contain the expected "/" character`, key)
		return nil
	}
	networkAddr := networkAddress{network: network, ip: ip}

	// 2. Workload by IP
	if wls := a.workloads.ByAddress.Lookup(networkAddr); len(wls) > 0 {
		return dedupeWorkloads(wls)
	}

	// 3. Service
	if svc := a.lookupService(key); svc != nil {
		res := []model.AddressInfo{serviceToAddressInfo(svc.Service)}
		for _, w := range a.workloads.ByServiceKey.Lookup(svc.ResourceName()) {
			res = append(res, workloadToAddressInfo(w.Workload))
		}
		return res
	}
	return nil
}

func (a *index) lookupService(key string) *model.ServiceInfo {
	// 1. namespace/hostname format
	s := a.services.GetKey(krt.Key[model.ServiceInfo](key))
	if s != nil {
		return s
	}

	// 2. network/ip format
	network, ip, _ := strings.Cut(key, "/")
	services := a.services.ByAddress.Lookup(networkAddress{
		network: network,
		ip:      ip,
	})
	return slices.First(services)
}

// All return all known workloads. Result is un-ordered
func (a *index) All() []model.AddressInfo {
	res := dedupeWorkloads(a.workloads.List())
	for _, s := range a.services.List() {
		res = append(res, serviceToAddressInfo(s.Service))
	}
	return res
}

func dedupeWorkloads(workloads []model.WorkloadInfo) []model.AddressInfo {
	if len(workloads) <= 1 {
		return slices.Map(workloads, modelWorkloadToAddressInfo)
	}
	res := []model.AddressInfo{}
	seenAddresses := sets.New[netip.Addr]()
	for _, wl := range workloads {
		write := true
		// HostNetwork mode is expected to have overlapping IPs, and tells the data plane to avoid relying on the IP as a unique
		// identifier.
		// For anything else, exclude duplicates.
		if wl.NetworkMode != workloadapi.NetworkMode_HOST_NETWORK {
			for _, addr := range wl.Addresses {
				a := byteIPToAddr(addr)
				if seenAddresses.InsertContains(a) {
					// We have already seen this address. We don't want to include it.
					// We do want to prefer Pods > WorkloadEntry to give precedence to Kubernetes. However, the underlying `a.workloads`
					// already guarantees this, so no need to handle it here.
					write = false
					break
				}
			}
		}
		if write {
			res = append(res, workloadToAddressInfo(wl.Workload))
		}
	}
	return res
}

// AddressInformation returns all AddressInfo's in the cluster.
// This may be scoped to specific subsets by specifying a non-empty addresses field
func (a *index) AddressInformation(addresses sets.String) ([]model.AddressInfo, sets.String) {
	if len(addresses) == 0 {
		// Full update
		return a.All(), nil
	}
	var res []model.AddressInfo
	var removed []string
	got := sets.New[string]()
	for wname := range addresses {
		wl := a.Lookup(wname)
		if len(wl) == 0 {
			removed = append(removed, wname)
		} else {
			for _, addr := range wl {
				if !got.InsertContains(addr.ResourceName()) {
					res = append(res, addr)
				}
			}
		}
	}
	return res, sets.New(removed...)
}

func (a *index) ServicesForWaypoint(key model.WaypointKey) []model.ServiceInfo {
	var out []model.ServiceInfo
	for _, host := range key.Hostnames {
		out = append(out, a.services.ByOwningWaypoint.Lookup(NamespaceHostname{
			Namespace: key.Namespace,
			Hostname:  host,
		})...)
	}
	return out
}

func (a *index) WorkloadsForWaypoint(key model.WaypointKey) []model.WorkloadInfo {
	var out []model.WorkloadInfo
	for _, host := range key.Hostnames {
		out = append(out, a.workloads.ByOwningWaypoint.Lookup(NamespaceHostname{
			Namespace: key.Namespace,
			Hostname:  host,
		})...)
	}
	out = model.SortWorkloadsByCreationTime(out)
	return out
}

func (a *index) AdditionalPodSubscriptions(
	proxy *model.Proxy,
	allAddresses sets.String,
	currentSubs sets.String,
) sets.String {
	shouldSubscribe := sets.New[string]()

	// First, we want to handle VIP subscriptions. Example:
	// Client subscribes to VIP1. Pod1, part of VIP1, is sent.
	// The client wouldn't be explicitly subscribed to Pod1, so it would normally ignore it.
	// Since it is a part of VIP1 which we are subscribe to, add it to the subscriptions
	for addr := range allAddresses {
		for _, wl := range model.ExtractWorkloadsFromAddresses(a.Lookup(addr)) {
			// We may have gotten an update for Pod, but are subscribed to a Service.
			// We need to force a subscription on the Pod as well
			for namespacedHostname := range wl.Services {
				if currentSubs.Contains(namespacedHostname) {
					shouldSubscribe.Insert(wl.ResourceName())
					break
				}
			}
		}
	}

	// Next, as an optimization, we will send all node-local endpoints
	if nodeName := proxy.Metadata.NodeName; nodeName != "" {
		for _, wl := range model.ExtractWorkloadsFromAddresses(a.All()) {
			if wl.Node == nodeName {
				n := wl.ResourceName()
				if currentSubs.Contains(n) {
					continue
				}
				shouldSubscribe.Insert(n)
			}
		}
	}

	return shouldSubscribe
}

func (a *index) SyncAll() {
	a.networkUpdateTrigger.TriggerRecomputation()
}

func (a *index) NetworksSynced() {
	a.networkUpdateTrigger.MarkSynced()
}

func (a *index) Run(stop <-chan struct{}) {
	if a.statusQueue != nil {
		go a.statusQueue.Run(stop)
	}
}

func (a *index) HasSynced() bool {
	return a.services.Synced().HasSynced() &&
		a.workloads.Synced().HasSynced() &&
		a.waypoints.Synced().HasSynced() &&
		a.authorizationPolicies.Synced().HasSynced()
}

type (
	LookupNetwork         func(endpointIP string, labels labels.Instance) network.ID
	LookupNetworkGateways func() []model.NetworkGateway
)

func PushXds[T any](xds model.XDSUpdater, f func(T) (model.ConfigKey, bool)) func(events []krt.Event[T], initialSync bool) {
	return func(events []krt.Event[T], initialSync bool) {
		cu := sets.New[model.ConfigKey]()
		for _, e := range events {
			for _, i := range e.Items() {
				c, nop := f(i)
				if !nop {
					cu.Insert(c)
				}
			}
		}
		xds.ConfigUpdate(&model.PushRequest{
			Full:           false,
			ConfigsUpdated: cu,
			Reason:         model.NewReasonStats(model.AmbientUpdate),
		})
	}
}
