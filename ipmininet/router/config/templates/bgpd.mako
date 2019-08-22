hostname ${node.name}
password ${node.password}

% if node.bgpd.logfile:
log file ${node.bgpd.logfile}
% endif

% for section in node.bgpd.debug:
debug bgp ${section}
% endfor

router bgp ${node.bgpd.asn}
    bgp router-id ${node.bgpd.routerid}
    bgp bestpath compare-routerid
    no bgp default ipv4-unicast
% for n in node.bgpd.neighbors:
    no auto-summary
    neighbor ${n.peer} remote-as ${n.asn}
    neighbor ${n.peer} port ${n.port}
    neighbor ${n.peer} description ${n.description}
    % if n.ebgp_multihop:
    neighbor ${n.peer} ebgp-multihop
    % endif
    <%block name="neighbor"/>
% endfor
% for af in node.bgpd.address_families:
    address-family ${af.name}
    % for rm in node.bgpd.route_maps:
        % if rm.neighbor.family == af.name:
            % if rm.on_input:
    neighbor ${rm.neighbor.peer} route-map ${rm.name} in
            % else:
    neighbor ${rm.neighbor.peer} route-map ${rm.name} out
            % endif
        % endif
    % endfor
    % for net in af.networks:
    network ${net.with_prefixlen}
    % endfor
    % for r in af.redistribute:
    redistribute ${r}
    % endfor
    % for n in af.neighbors:
        % if n.family == af.name:
    neighbor ${n.peer} activate
            % if n.nh_self:
    neighbor ${n.peer} ${n.nh_self}
            % endif
        % endif
    % endfor
    %for rr in node.bgpd.rr:
        %if rr.family == af.name:
    neighbor ${rr.peer} route-reflector-client
        %endif
    %endfor
% endfor

% for al in node.bgpd.access_lists:
    % for e in al.entries:
ipv6 access-list ${al.name} ${e.prefix} ${e.action}
    % endfor
% endfor

% for rm in node.bgpd.route_maps:
route-map ${rm.name} ${rm.match_policy} ${rm.order}
    %for match in rm.match_cond:
        %if match.type == "access_list":
    match ipv6 address ${match.condition}
        %endif
        %if match.type != "access_list":
    match ipv6 address ${match.type} ${match.condition}
        %endif
    %endfor
   %for action in rm.set_actions:
       %if action.type == 'community':
    set ${action.type} ${rm.neighbor.asn}:${action.value}
       %else:
    set ${action.type} ${action.value}
       %endif
   %endfor
% endfor
<%block name="router"/>
!
