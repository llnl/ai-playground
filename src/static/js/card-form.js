(() => {
  // All profile forms are rendered by Django. Show only the profile matching
  // the shared resource_type field so users can switch types without a request.
  const resourceType = document.querySelector("#id_resource_type");
  const profileSections = document.querySelectorAll("[data-profile-section]");

  function showSelectedProfile() {
    if (!resourceType) return;
    profileSections.forEach((section) => {
      const selected = section.dataset.profileSection === resourceType.value;
      section.hidden = !selected;
      // Hidden controls must also be disabled. Otherwise their values would be
      // submitted alongside the selected profile and could collide or confuse
      // server-side processing.
      section.querySelectorAll("input, select, textarea").forEach((field) => {
        field.disabled = !selected;
      });
    });
    const title = document.querySelector("[data-profile-title]");
    const labels = { mcp_server: "MCP server", agent: "Agent", skill: "Skill" };
    if (title) title.textContent = labels[resourceType.value] || "Resource";
  }

  resourceType?.addEventListener("change", showSelectedProfile);
  showSelectedProfile();

  // Owner rows use a Django formset. TOTAL_FORMS and each row's numeric prefix
  // must stay in sync for Django to reconstruct all submitted owner forms.
  const ownerList = document.querySelector("#owner-list");
  const totalForms = document.querySelector("#id_owners-TOTAL_FORMS");
  const template = document.querySelector("#empty-owner-form");
  const removeOwnerModal = document.querySelector("#remove-owner-modal");
  let ownerPendingRemoval = null;

  function renumberOwners() {
    // These numbers are display-only. Existing field indexes are intentionally
    // left unchanged because Django formsets permit gaps when rows are deleted.
    ownerList?.querySelectorAll("[data-owner-form]:not([hidden])").forEach((owner, index) => {
      const number = owner.querySelector("[data-owner-number]");
      if (number) number.textContent = index + 1;
    });
  }

  document.querySelector("#add-owner")?.addEventListener("click", () => {
    if (!ownerList || !totalForms || !template) return;
    const index = Number(totalForms.value);
    const wrapper = document.createElement("div");
    // Django's empty_form template uses __prefix__ as the placeholder for every
    // name and id belonging to the new formset row.
    wrapper.innerHTML = template.innerHTML.replaceAll("__prefix__", index);
    ownerList.append(wrapper.firstElementChild);
    totalForms.value = index + 1;
    renumberOwners();
  });

  ownerList?.addEventListener("click", (event) => {
    // Event delegation also handles remove buttons in rows added after load.
    const button = event.target.closest("[data-remove-owner]");
    if (!button) return;
    const owner = button.closest("[data-owner-form]");
    if (!owner || !removeOwnerModal) return;
    ownerPendingRemoval = owner;
    const ownerName = owner.querySelector('input[name$="-owner_name"]')?.value.trim();
    const ownerNameDisplay = removeOwnerModal.querySelector("[data-remove-owner-name]");
    if (ownerNameDisplay) ownerNameDisplay.textContent = ownerName ? `“${ownerName}”` : "This owner";
    removeOwnerModal.showModal();
  });

  function removePendingOwner() {
    if (!ownerPendingRemoval) return;
    const deleteField = ownerPendingRemoval.querySelector('input[name$="-DELETE"]');
    if (deleteField) {
      // Mark the Django formset row for deletion instead of removing its fields.
      // This lets update requests delete owners that already exist in initial data.
      deleteField.checked = true;
      ownerPendingRemoval.hidden = true;
    } else {
      // This fallback applies only if markup without a can_delete field is used.
      ownerPendingRemoval.remove();
    }
    ownerPendingRemoval = null;
    removeOwnerModal?.close();
    renumberOwners();
  }

  removeOwnerModal?.querySelector("[data-confirm-remove-owner]")?.addEventListener("click", removePendingOwner);
  removeOwnerModal?.querySelector("[data-cancel-remove-owner]")?.addEventListener("click", () => {
    ownerPendingRemoval = null;
    removeOwnerModal.close();
  });
  removeOwnerModal?.addEventListener("close", () => {
    ownerPendingRemoval = null;
  });

  renumberOwners();

  // Repeatable values remain real textarea fields in the HTML so the form works
  // without JavaScript. Enhancement hides each textarea, builds friendlier rows,
  // and continuously serializes row values back into that textarea for Django.
  function enhanceList(textarea) {
    // Avoid enhancing the same textarea twice when a newly added owner is scanned.
    if (textarea.closest(".js-enhanced-list")) return;
    const container = document.createElement("div");
    container.className = "repeatable-list";
    textarea.parentNode.insertBefore(container, textarea);
    container.append(textarea);
    container.classList.add("js-enhanced-list");

    const rows = document.createElement("div");
    rows.className = "repeatable-list__rows";
    container.append(rows);

    const listType = textarea.dataset.repeatable;
    // data-repeatable selects labels, button text, and the generated input type.
    const labels = {
      emails: { item: "Contact email", add: "+ Add another email", inputType: "email" },
      institutions: { item: "Institution", add: "+ Add another institution", inputType: "text" },
      tags: { item: "Tag", add: "+ Add another tag", inputType: "text" },
      items: { item: "Item", add: "+ Add another item", inputType: "text" },
    };
    const listLabels = labels[listType] || labels.institutions;
    const itemPlaceholder = textarea.getAttribute("placeholder") || `Example ${listLabels.item.toLowerCase()}`;

    // A lone blank row is the empty state, so removing it would add no value.
    // Keep its Remove action disabled until it contains data or another row exists.
    const updateRemoveButtons = () => {
      const repeatableRows = [...rows.querySelectorAll(".repeatable-row")];
      repeatableRows.forEach((row) => {
        const remove = row.querySelector(".repeatable-remove");
        const input = row.querySelector("input");
        if (remove) remove.disabled = repeatableRows.length === 1 && !input?.value.trim();
      });
    };

    const sync = () => {
      // StringListField parses one non-empty value per line for tags and other
      // JSON-backed string lists.
      textarea.value = [...rows.querySelectorAll("input")]
        .map((input) => input.value.trim())
        .filter(Boolean)
        .join("\n");
    };

    const addRow = (value = "") => {
      const row = document.createElement("div");
      row.className = "repeatable-row";
      const fields = document.createDocumentFragment();
      const input = document.createElement("input");
      input.type = listLabels.inputType;
      input.value = value;
      input.setAttribute("aria-label", listLabels.item);
      input.placeholder = itemPlaceholder;
      input.addEventListener("input", () => {
        sync();
        updateRemoveButtons();
      });
      fields.append(input);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "repeatable-remove";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        row.remove();
        // Keep one blank row visible so an emptied list remains easy to refill.
        if (!rows.children.length) addRow();
        sync();
        updateRemoveButtons();
      });
      row.append(fields, remove);
      rows.append(row);
      updateRemoveButtons();
    };

    // Rehydrate repeatable controls from initial model data or values returned
    // after a server-side validation error.
    textarea.value.split(/\r?\n/).filter(Boolean).forEach(addRow);
    if (!rows.children.length) addRow();

    const add = document.createElement("button");
    add.type = "button";
    add.className = "repeatable-add";
    add.textContent = listLabels.add;
    add.addEventListener("click", () => addRow());
    container.append(add);
  }

  function enhanceOwnerLists(root = document) {
    // The selector covers ownership fields, shared tags, and all profile lists.
    root.querySelectorAll("textarea[data-repeatable]").forEach(enhanceList);
  }

  enhanceOwnerLists();

  const addOwner = document.querySelector("#add-owner");
  addOwner?.addEventListener("click", () => {
    // The owner-creation handler runs first, then this handler enhances only the
    // newly appended row's email and institution textareas.
    const owners = ownerList?.querySelectorAll("[data-owner-form]");
    if (owners?.length) enhanceOwnerLists(owners[owners.length - 1]);
  });

  // MCP tools use a real Django formset rather than a hidden delimiter format.
  // New rows receive indexed names such as tools-1-name and tools-1-description.
  const toolList = document.querySelector("[data-tool-list]");
  const toolTotalForms = document.querySelector("#id_tools-TOTAL_FORMS");
  const emptyToolForm = document.querySelector("#empty-tool-form");

  function updateToolRemoveButtons() {
    const visibleTools = [...(toolList?.querySelectorAll("[data-tool-form]:not([hidden])") || [])];
    visibleTools.forEach((tool) => {
      const remove = tool.querySelector("[data-remove-tool]");
      const inputs = [...tool.querySelectorAll('input:not([name$="-DELETE"])')];
      const isEmpty = inputs.every((input) => !input.value.trim());
      if (remove) remove.disabled = visibleTools.length === 1 && isEmpty;
    });
  }

  function renumberTools() {
    toolList?.querySelectorAll("[data-tool-form]:not([hidden])").forEach((tool, index) => {
      const number = tool.querySelector("[data-tool-number]");
      if (number) number.textContent = index + 1;
    });
  }

  document.querySelector("[data-add-tool]")?.addEventListener("click", () => {
    if (!toolList || !toolTotalForms || !emptyToolForm) return;
    const index = Number(toolTotalForms.value);
    const wrapper = document.createElement("div");
    wrapper.innerHTML = emptyToolForm.innerHTML.replaceAll("__prefix__", index);
    toolList.append(wrapper.firstElementChild);
    toolTotalForms.value = index + 1;
    renumberTools();
    updateToolRemoveButtons();
  });

  toolList?.addEventListener("input", updateToolRemoveButtons);

  toolList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-tool]");
    if (!button) return;
    const tool = button.closest("[data-tool-form]");
    if (!tool) return;
    const deleteField = tool.querySelector('input[name$="-DELETE"]');
    if (deleteField) {
      deleteField.checked = true;
      tool.hidden = true;
    } else {
      tool.remove();
    }
    renumberTools();
    updateToolRemoveButtons();
  });

  renumberTools();
  updateToolRemoveButtons();
})();
